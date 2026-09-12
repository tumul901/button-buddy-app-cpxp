import React, { createContext, useContext, useEffect, useMemo, useReducer, useRef } from 'react';
import type { ReactNode } from 'react';

import type { AppAction, AppState, BadgeItem, CropState, PrintConfig } from './types';

// ─────────────────────────────────────────────────────────────────
//  Defaults
// ─────────────────────────────────────────────────────────────────

export const DEFAULT_CROP: CropState = { offsetX: 0, offsetY: 0, scale: 1.0 };

const defaultPrintConfig: PrintConfig = {
  paper: 'A4',
  orientation: 'portrait',
  copies: 'auto',
  gapMm: 5,
  marginMm: 10,
  includeRuler: true,
  drawGuides: true,
  perforationMm: 12,
};

const initialState: AppState = {
  step: 'input',
  diameterMm: 58,
  bleedMm: 0,
  selectedTemplateId: null,
  printConfig: defaultPrintConfig,
  badges: [],
  activeBadgeId: null,
  isBusy: false,
  error: null,
  hydrated: false,
};

// ─────────────────────────────────────────────────────────────────
//  Persistence
//
//  v1 kept everything in memory, so a single refresh destroyed an entire
//  batch — brutal for the event/kiosk use case this app is built for.
//  Badges now reference server-side session URLs, so the persisted blob is
//  small and rehydrates into a fully working session.
// ─────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'buttonbuddy.session.v2';

interface PersistedShape {
  diameterMm: number;
  bleedMm: number;
  selectedTemplateId: string | null;
  printConfig: PrintConfig;
  badges: BadgeItem[];
  activeBadgeId: string | null;
  savedAt: number;
}

function loadPersisted(): Partial<AppState> | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PersistedShape;
    if (!Array.isArray(parsed.badges)) return null;

    // Anything older than a day is very likely swept server-side already.
    if (Date.now() - (parsed.savedAt ?? 0) > 24 * 60 * 60 * 1000) {
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }

    return {
      diameterMm: parsed.diameterMm ?? initialState.diameterMm,
      bleedMm: parsed.bleedMm ?? initialState.bleedMm,
      selectedTemplateId: parsed.selectedTemplateId ?? null,
      printConfig: { ...defaultPrintConfig, ...(parsed.printConfig ?? {}) },
      // An in-flight upload cannot survive a reload; mark those failed so the
      // user sees something honest instead of a spinner that never resolves.
      badges: parsed.badges.map((b) => ({
        ...b,
        status: b.status === 'uploading' || b.status === 'rendering' ? 'idle' : b.status,
      })),
      activeBadgeId: parsed.activeBadgeId ?? null,
    };
  } catch {
    // Corrupt or unavailable storage must never block the app from loading.
    return null;
  }
}

function persist(state: AppState): void {
  try {
    const payload: PersistedShape = {
      diameterMm: state.diameterMm,
      bleedMm: state.bleedMm,
      selectedTemplateId: state.selectedTemplateId,
      printConfig: state.printConfig,
      badges: state.badges,
      activeBadgeId: state.activeBadgeId,
      savedAt: Date.now(),
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  } catch {
    // Private mode / quota exceeded. Losing persistence is survivable.
  }
}

export function clearPersisted(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

// ─────────────────────────────────────────────────────────────────
//  Reducer
// ─────────────────────────────────────────────────────────────────

function pickNextActive(badges: BadgeItem[], removedId: string, current: string | null): string | null {
  if (current !== removedId) return current;
  return badges.length > 0 ? (badges[0] as BadgeItem).id : null;
}

function reducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case 'HYDRATE':
      return { ...state, ...action.payload, hydrated: true };

    case 'SET_STEP':
      return { ...state, step: action.payload };

    case 'SET_DIAMETER':
      // Composites are deliberately NOT cleared: the old render stays visible
      // while `isStale()` marks it, so the user keeps their preview and gets a
      // clear "re-render" prompt rather than a blank editor.
      return { ...state, diameterMm: action.payload };

    case 'SET_BLEED':
      return { ...state, bleedMm: action.payload };

    case 'SET_TEMPLATE': {
      const id = action.payload;
      return {
        ...state,
        selectedTemplateId: id,
        badges: state.badges.map((b) =>
          b.id === state.activeBadgeId
            ? { ...b, templateId: id, compositeUrl: null, status: 'idle', error: null }
            : b,
        ),
      };
    }

    case 'APPLY_TEMPLATE_TO_ALL': {
      const id = action.payload;
      return {
        ...state,
        selectedTemplateId: id,
        badges: state.badges.map((b) => ({
          ...b,
          templateId: id,
          compositeUrl: null,
          status: 'idle',
          error: null,
        })),
      };
    }

    case 'SET_PRINT_CONFIG':
      return { ...state, printConfig: { ...state.printConfig, ...action.payload } };

    case 'ADD_BADGES': {
      if (action.payload.length === 0) return state;
      const badges = [...state.badges, ...action.payload];
      const first = action.payload[0] as BadgeItem;
      return {
        ...state,
        badges,
        activeBadgeId: state.activeBadgeId ?? first.id,
      };
    }

    case 'UPDATE_BADGE': {
      const { id, changes } = action.payload;
      return {
        ...state,
        badges: state.badges.map((b) => (b.id === id ? { ...b, ...changes } : b)),
      };
    }

    case 'SET_CROP': {
      const { id, crop } = action.payload;
      return {
        ...state,
        badges: state.badges.map((b) => (b.id === id ? { ...b, crop } : b)),
      };
    }

    case 'REMOVE_BADGE': {
      const badges = state.badges.filter((b) => b.id !== action.payload);
      return {
        ...state,
        badges,
        activeBadgeId: pickNextActive(badges, action.payload, state.activeBadgeId),
      };
    }

    case 'SET_ACTIVE_BADGE': {
      const item = state.badges.find((b) => b.id === action.payload);
      if (!item) return state;
      return {
        ...state,
        activeBadgeId: action.payload,
        // Follow the badge's own template so the selector reflects the selection.
        selectedTemplateId: item.templateId ?? state.selectedTemplateId,
      };
    }

    case 'SET_BUSY':
      return { ...state, isBusy: action.payload };

    case 'SET_ERROR':
      return { ...state, error: action.payload };

    case 'RESET':
      return { ...initialState, hydrated: true };

    default:
      return state;
  }
}

// ─────────────────────────────────────────────────────────────────
//  Context
// ─────────────────────────────────────────────────────────────────

interface AppContextValue {
  state: AppState;
  dispatch: React.Dispatch<AppAction>;
  activeBadge: BadgeItem | null;
}

const AppContext = createContext<AppContextValue | undefined>(undefined);

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const saveTimer = useRef<number | null>(null);

  // Restore once, before first paint, so guards do not bounce a valid session.
  useEffect(() => {
    const restored = loadPersisted();
    dispatch({ type: 'HYDRATE', payload: restored ?? {} });
  }, []);

  // Debounced save: dragging a slider must not hammer localStorage.
  useEffect(() => {
    if (!state.hydrated) return;
    if (saveTimer.current !== null) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => persist(state), 300);
    return () => {
      if (saveTimer.current !== null) window.clearTimeout(saveTimer.current);
    };
  }, [state]);

  const activeBadge = useMemo(
    () => state.badges.find((b) => b.id === state.activeBadgeId) ?? null,
    [state.badges, state.activeBadgeId],
  );

  const value = useMemo(
    () => ({ state, dispatch, activeBadge }),
    [state, activeBadge],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used inside AppProvider');
  return ctx;
}
