/**
 * The tray of badges that will go on the sheet.
 *
 * Every item shows its own status, so a batch reports real per-photo progress
 * and one failure is visible and retryable instead of silently poisoning the
 * run. Uploads go through the same validated path as the drop zone — v1's
 * tray skipped type and size checks entirely.
 */

import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import './BadgeTray.css';
import { assetUrl } from '../../api/client';
import { useApp } from '../../store/AppContext';
import { useBadgeActions } from '../../hooks/useBadgeActions';
import { isStale } from '../../store/types';
import type { BadgeItem } from '../../store/types';
import { CameraCapture } from '../CameraCapture/CameraCapture';

const MAX_COPIES = 500;

function StatusChip({ badge, diameterMm, bleedMm }: { badge: BadgeItem; diameterMm: number; bleedMm: number }) {
  if (badge.status === 'uploading') return <span className="bt-chip uploading">Uploading…</span>;
  if (badge.status === 'rendering') return <span className="bt-chip rendering">Rendering…</span>;
  if (badge.status === 'failed') return <span className="bt-chip failed">Failed</span>;
  if (badge.status === 'ready' && isStale(badge, diameterMm, bleedMm)) {
    return <span className="bt-chip stale">Re-render</span>;
  }
  if (badge.status === 'ready') return <span className="bt-chip ready">✓ Ready</span>;
  return <span className="bt-chip idle">Not rendered</span>;
}

export function BadgeTray() {
  const { state, dispatch } = useApp();
  const { badges, activeBadgeId, selectedTemplateId, diameterMm, bleedMm, isBusy } = state;
  const { addPhotos, renderBadges, cancel } = useBadgeActions();

  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [showCamera, setShowCamera] = useState(false);

  const totalCopies = badges.reduce((sum, b) => sum + (b.copies || 1), 0);
  const readyCount = badges.filter((b) => b.status === 'ready' && !isStale(b, diameterMm, bleedMm)).length;

  const unrenderedBadges = badges.filter(
    (b) => b.status !== 'ready' || !b.compositeUrl || isStale(b, diameterMm, bleedMm),
  );

  const goToRender = (badgeId: string) => {
    dispatch({ type: 'SET_ACTIVE_BADGE', payload: badgeId });
    dispatch({ type: 'SET_STEP', payload: 'editor' });
    navigate('/editor');
    window.setTimeout(() => {
      const btn = document.getElementById('btn-render');
      if (btn) {
        btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
        btn.classList.add('pulse-highlight');
        window.setTimeout(() => btn.classList.remove('pulse-highlight'), 1800);
        btn.focus();
      }
    }, 80);
  };

  const handleFiles = (files: File[]) => void addPhotos(files);

  const setCopies = (badge: BadgeItem, next: number) => {
    dispatch({
      type: 'UPDATE_BADGE',
      payload: { id: badge.id, changes: { copies: Math.max(1, Math.min(MAX_COPIES, next)) } },
    });
  };

  return (
    <div className="badge-tray" role="region" aria-label="Badges for this sheet">
      <div className="bt-header">
        <div className="bt-title-row">
          <span className="bt-title">Badges on this sheet</span>
          <span className="badge badge-accent">
            {badges.length} photo{badges.length === 1 ? '' : 's'} · {totalCopies} printout
            {totalCopies === 1 ? '' : 's'}
            {badges.length > 0 && ` · ${readyCount} ready`}
          </span>
        </div>

        <div className="bt-actions">
          {isBusy && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={cancel}>
              ✕ Cancel
            </button>
          )}
          {unrenderedBadges.length > 0 && (
            <>
              <button
                type="button"
                id="btn-tray-go-render"
                className="btn btn-primary btn-sm"
                onClick={() => {
                  const target =
                    unrenderedBadges.find((b) => b.id === activeBadgeId) || unrenderedBadges[0];
                  if (target) goToRender(target.id);
                }}
                disabled={isBusy}
                title="Open in editor to frame and render with applied settings"
              >
                ✦ Go to render ({unrenderedBadges.length})
              </button>
              <button
                type="button"
                id="btn-tray-render-all-unrendered"
                className="btn btn-accent btn-sm"
                onClick={() => void renderBadges(unrenderedBadges.map((b) => b.id))}
                disabled={isBusy}
                title="Render all unrendered badges with applied settings directly"
              >
                ⚡ Render with applied settings
              </button>
            </>
          )}
          {selectedTemplateId && badges.length > 1 && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => dispatch({ type: 'APPLY_TEMPLATE_TO_ALL', payload: selectedTemplateId })}
              disabled={isBusy}
              title="Give every badge the currently selected template"
            >
              🎨 Same template for all
            </button>
          )}
          <button
            type="button"
            id="btn-tray-camera"
            className="btn btn-secondary btn-sm"
            onClick={() => setShowCamera(true)}
            disabled={isBusy}
          >
            📷 Camera
          </button>
        </div>
      </div>

      <div className="bt-scroll">
        {badges.map((b, idx) => {
          const isActive = b.id === activeBadgeId;
          const stale = isStale(b, diameterMm, bleedMm);
          const isUnrendered = b.status !== 'ready' || !b.compositeUrl || stale;
          // Composite URLs are version-stamped by the backend, so the browser
          // shows the newest render without any ad-hoc cache-busting.
          const src = b.compositeUrl
            ? assetUrl(b.compositeUrl)
            : b.photoUrl
              ? assetUrl(b.photoUrl)
              : '';

          return (
            <div
              key={b.id}
              className={`bt-item ${isActive ? 'active' : ''} ${b.status === 'failed' ? 'failed' : ''}`}
              onClick={() => dispatch({ type: 'SET_ACTIVE_BADGE', payload: b.id })}
              role="button"
              tabIndex={0}
              aria-pressed={isActive}
              aria-label={`Badge ${idx + 1}${isActive ? ', selected' : ''}`}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  dispatch({ type: 'SET_ACTIVE_BADGE', payload: b.id });
                }
              }}
              title={b.error ?? undefined}
            >
              <div className={`bt-thumb-wrap ${stale && b.compositeUrl ? 'stale' : ''}`}>
                {src ? (
                  <img src={src} alt="" className="bt-thumb" loading="lazy" />
                ) : (
                  <div className="bt-thumb placeholder"><span className="spinner" /></div>
                )}
              </div>

              <span className="bt-item-name">Badge {idx + 1}</span>
              <StatusChip badge={b} diameterMm={diameterMm} bleedMm={bleedMm} />

              {isUnrendered && (
                <button
                  type="button"
                  className="bt-go-render-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    goToRender(b.id);
                  }}
                  title="Go to editor to frame and render with applied settings"
                >
                  Go to render →
                </button>
              )}

              {/* The reason belongs on the card, not only in a tooltip. */}
              {b.status === 'failed' && b.error && (
                <span className="bt-item-error">{b.error}</span>
              )}

              <div className="bt-copies-stepper" onClick={(e) => e.stopPropagation()}>
                <button
                  type="button"
                  className="bt-step-btn"
                  onClick={() => setCopies(b, (b.copies || 1) - 1)}
                  disabled={(b.copies || 1) <= 1}
                  aria-label={`One fewer copy of badge ${idx + 1}`}
                >
                  −
                </button>
                <span className="bt-copies-count">{b.copies || 1}</span>
                <button
                  type="button"
                  className="bt-step-btn"
                  onClick={() => setCopies(b, (b.copies || 1) + 1)}
                  disabled={(b.copies || 1) >= MAX_COPIES}
                  aria-label={`One more copy of badge ${idx + 1}`}
                >
                  +
                </button>
              </div>

              <div className="bt-item-tools" onClick={(e) => e.stopPropagation()}>
                {isUnrendered &&
                  b.status !== 'rendering' &&
                  b.status !== 'uploading' && (
                    <button
                      type="button"
                      className="bt-quick-render-btn"
                      onClick={() => void renderBadges([b.id])}
                      disabled={isBusy}
                      title="Render with applied settings"
                    >
                      ⚡ Render
                    </button>
                  )}
                {b.status === 'failed' && b.sessionId && (
                  <button
                    type="button"
                    className="bt-retry-btn"
                    onClick={() => void renderBadges([b.id])}
                    disabled={isBusy}
                  >
                    Retry
                  </button>
                )}
                <button
                  type="button"
                  className="bt-delete-btn"
                  onClick={() => dispatch({ type: 'REMOVE_BADGE', payload: b.id })}
                  aria-label={`Remove badge ${idx + 1}`}
                  title="Remove from sheet"
                >
                  ✕
                </button>
              </div>
            </div>
          );
        })}

        <button
          type="button"
          id="btn-tray-add-photo"
          className="bt-add-card"
          onClick={() => fileInputRef.current?.click()}
          disabled={isBusy}
        >
          <span className="bt-add-icon">＋</span>
          <span className="bt-add-text">Add photos</span>
        </button>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept="image/jpeg,image/png,image/webp"
        style={{ display: 'none' }}
        onChange={(e) => {
          if (e.target.files) handleFiles(Array.from(e.target.files));
          e.target.value = '';
        }}
      />

      {showCamera && (
        <div
          className="bt-modal-backdrop"
          onClick={() => setShowCamera(false)}
          role="dialog"
          aria-modal="true"
          aria-label="Capture photos"
        >
          <div className="bt-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="bt-modal-header">
              <h3>Capture photos</h3>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setShowCamera(false)}>
                ✕ Close
              </button>
            </div>
            <CameraCapture
              initialMode="batch"
              onCapture={(file) => {
                handleFiles([file]);
                setShowCamera(false);
              }}
              onBatchCapture={(files) => {
                handleFiles(files);
                setShowCamera(false);
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
