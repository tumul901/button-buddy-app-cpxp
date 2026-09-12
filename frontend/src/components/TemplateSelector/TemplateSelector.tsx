/**
 * Branding template picker.
 *
 * "No frame" is a first-class option: a plain photo badge is a legitimate
 * product, and v1 made a template mandatory — so an empty template table left
 * the user stuck in the editor with a permanently disabled Render button.
 */

import './TemplateSelector.css';
import { assetUrl } from '../../api/client';
import { useApp } from '../../store/AppContext';
import type { BadgeTemplate } from '../../store/types';

interface Props {
  templates: BadgeTemplate[];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}

export function TemplateSelector({ templates, loading, error, onRetry }: Props) {
  const { state, dispatch } = useApp();
  const { activeBadgeId, badges } = state;
  const activeBadge = badges.find((b) => b.id === activeBadgeId) ?? null;
  const selectedId = activeBadge?.templateId ?? null;

  const select = (id: string | null) => dispatch({ type: 'SET_TEMPLATE', payload: id });

  if (loading) {
    return (
      <div className="template-selector">
        <span className="label">Frame</span>
        <div className="ts-loading">
          <span className="spinner" /> Loading frames…
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="template-selector">
        <span className="label">Frame</span>
        <div className="error-banner" role="alert">
          ⚠️ {error}
          <button type="button" className="btn btn-ghost btn-sm" onClick={onRetry}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="template-selector">
      <span className="label">Frame {activeBadge ? '' : '(select a badge first)'}</span>
      <div className="template-grid">
        <button
          type="button"
          id="tpl-none"
          className={`template-card ${selectedId === null ? 'selected' : ''}`}
          onClick={() => select(null)}
          disabled={!activeBadge}
          aria-pressed={selectedId === null}
        >
          <span className="template-thumb template-none">🚫</span>
          <span className="template-name">No frame</span>
          {selectedId === null && <span className="template-check">✓</span>}
        </button>

        {templates.map((tpl) => (
          <button
            key={tpl.id}
            type="button"
            id={`tpl-${tpl.id}`}
            className={`template-card ${selectedId === tpl.id ? 'selected' : ''}`}
            onClick={() => select(tpl.id)}
            disabled={!activeBadge}
            aria-pressed={selectedId === tpl.id}
            title={tpl.name}
          >
            <img
              src={assetUrl(tpl.thumbnail_url)}
              alt=""
              className="template-thumb"
              loading="lazy"
            />
            <span className="template-name">{tpl.name}</span>
            {selectedId === tpl.id && <span className="template-check">✓</span>}
          </button>
        ))}
      </div>

      {templates.length === 0 && (
        <p className="dc-hint">
          No branding frames are installed. Plain photo badges still work.
        </p>
      )}
    </div>
  );
}
