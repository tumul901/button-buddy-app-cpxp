import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import './EditorPage.css';
import { fetchTemplates, toApiError } from '../api/client';
import type { TemplateDto } from '../api/client';
import { BadgeTray } from '../components/BadgeTray/BadgeTray';
import { DiameterControl } from '../components/DiameterControl/DiameterControl';
import { TemplateEditor } from '../components/TemplateEditor/TemplateEditor';
import { TemplateSelector } from '../components/TemplateSelector/TemplateSelector';
import { useApp } from '../store/AppContext';
import { isPrintable } from '../store/types';

export function EditorPage() {
  const { state, dispatch } = useApp();
  const navigate = useNavigate();

  const [templates, setTemplates] = useState<TemplateDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetched once. v1 had `selectedTemplateId` in the dep array, so picking a
  // template re-fetched the entire list every single time.
  const load = useCallback(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchTemplates(controller.signal)
      .then((rows) => setTemplates(rows))
      .catch((err) => {
        const e = toApiError(err);
        if (!e.isCancel) setError(e.message);
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  useEffect(() => load(), [load]);

  // Wait for hydration before redirecting: bouncing a restored session back to
  // the home page on every refresh is exactly the bug we set out to fix.
  useEffect(() => {
    if (state.hydrated && state.badges.length === 0) navigate('/', { replace: true });
  }, [state.hydrated, state.badges.length, navigate]);

  const readyCount = state.badges.filter((b) =>
    isPrintable(b, state.diameterMm, state.bleedMm),
  ).length;

  return (
    <div className="editor-page fade-in-up">
      <div className="ep-tray-wrap">
        <BadgeTray />
      </div>

      <div className="ep-sidebar">
        <h2>Design</h2>
        <p className="ep-sub">
          Pick a badge from the tray, choose its frame, then drag or scroll the photo to frame it.
        </p>

        <DiameterControl />
        <TemplateSelector
          templates={templates}
          loading={loading}
          error={error}
          onRetry={load}
        />

        {state.error && <div className="error-banner" role="alert">⚠️ {state.error}</div>}

        <div className="ep-nav">
          <button
            id="btn-go-print"
            type="button"
            className="btn btn-accent btn-lg"
            onClick={() => {
              dispatch({ type: 'SET_STEP', payload: 'print' });
              navigate('/print');
            }}
            disabled={readyCount === 0}
            title={
              readyCount === 0
                ? 'Render at least one badge first'
                : `${readyCount} badge(s) ready to print`
            }
          >
            Next: print sheet →
          </button>
          {readyCount === 0 && (
            <span className="ep-nav-hint">Render a badge to continue</span>
          )}

          <button type="button" className="btn btn-ghost btn-sm" onClick={() => navigate('/')}>
            ← Back
          </button>
        </div>
      </div>

      <div className="ep-main">
        <TemplateEditor templates={templates} />
      </div>
    </div>
  );
}
