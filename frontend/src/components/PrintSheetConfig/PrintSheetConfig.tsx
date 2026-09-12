/**
 * Sheet layout controls, with a live true-to-scale diagram.
 *
 * The diagram is drawn from the same `computeLayout` the backend mirrors, so
 * what it shows is what the exporter will place — including refusing to draw
 * anything when the badge genuinely does not fit.
 */

import './PrintSheetConfig.css';
import { useApp } from '../../store/AppContext';
import { isPrintable } from '../../store/types';
import type { Orientation, PaperSize } from '../../utils/paperLayouts';
import { PAPER_LABELS, badgeOriginMm, cellSizeMm, computeLayout } from '../../utils/paperLayouts';
import { findBestFit } from '../../utils/autoFit';

const PAPERS: PaperSize[] = ['A4', 'A3', 'Letter', 'Legal', '4x6'];

export function PrintSheetConfig() {
  const { state, dispatch } = useApp();
  const { printConfig, diameterMm, bleedMm, badges } = state;
  const { paper, orientation, copies, gapMm, marginMm, includeRuler, drawGuides, perforationMm } =
    printConfig;

  const update = (partial: Partial<typeof printConfig>) =>
    dispatch({ type: 'SET_PRINT_CONFIG', payload: partial });

  const printable = badges.filter((b) => isPrintable(b, diameterMm, bleedMm));
  const isBatch = printable.length > 1;

  // In batch mode the tray's per-badge copy counts decide the total; the
  // single-badge "copies" control is meaningless there and is hidden.
  const trayTotal = printable.reduce((sum, b) => sum + (b.copies || 1), 0);
  const requested = isBatch ? trayTotal : copies === 'auto' ? undefined : copies;

  // The tiling cell must hold the cutter ring when that is the outer element,
  // or adjacent rings would overlap.
  const footprintMm = cellSizeMm(diameterMm, bleedMm, perforationMm);
  const layout = computeLayout(
    paper,
    orientation,
    footprintMm,
    gapMm,
    marginMm,
    requested,
    includeRuler ? undefined : 0,
  );

  // Offer a better arrangement when one exists, rather than making the user
  // discover it by dragging three sliders.
  const bestFit = findBestFit({
    paper,
    orientation,
    diameterMm,
    bleedMm,
    perforationMm,
    marginMm,
    gapMm,
    includeRuler,
  });

  const applyBestFit = () =>
    update({
      marginMm: bestFit.marginMm,
      gapMm: bestFit.gapMm,
      includeRuler: bestFit.includeRuler,
      orientation: bestFit.orientation,
    });

  const totalToPrint = isBatch ? trayTotal : layout.totalBadges;
  const pages = layout.fits ? Math.max(1, Math.ceil(totalToPrint / layout.capacityPerPage)) : 0;

  // ---- true-to-scale diagram -------------------------------------------
  const { w: pw, h: ph } = layout.paperMm;
  const SVG_W = 100;
  const SVG_H = (ph / pw) * SVG_W;
  const k = SVG_W / pw; // mm -> svg units

  const badgeSequence: number[] = [];
  if (isBatch) {
    printable.forEach((b, i) => {
      for (let c = 0; c < (b.copies || 1); c++) badgeSequence.push(i);
    });
  }

  const dots: { cx: number; cy: number; hue: number }[] = [];
  if (layout.fits) {
    const onFirstPage = Math.min(totalToPrint, layout.capacityPerPage);
    for (let slot = 0; slot < onFirstPage; slot++) {
      const o = badgeOriginMm(layout, slot);
      const idx = badgeSequence[slot];
      dots.push({
        cx: (o.x + footprintMm / 2) * k,
        cy: (o.y + footprintMm / 2) * k,
        hue: idx === undefined ? 262 : (idx * 67 + 262) % 360,
      });
    }
  }

  return (
    <div className="psc-wrap card-raised">
      <span className="label">Sheet</span>

      <div className="psc-grid">
        <div className="form-group">
          <label className="label" htmlFor="psc-paper">Paper</label>
          <select
            id="psc-paper"
            className="input select"
            value={paper}
            onChange={(e) => update({ paper: e.target.value as PaperSize })}
          >
            {PAPERS.map((p) => (
              <option key={p} value={p}>{PAPER_LABELS[p]}</option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label className="label" htmlFor="psc-orient">Orientation</label>
          <select
            id="psc-orient"
            className="input select"
            value={orientation}
            onChange={(e) => update({ orientation: e.target.value as Orientation })}
          >
            <option value="portrait">Portrait</option>
            <option value="landscape">Landscape</option>
          </select>
        </div>

        {!isBatch && (
          <div className="form-group">
            <label className="label" htmlFor="psc-copies-mode">Copies</label>
            <div className="psc-copies-row">
              <select
                id="psc-copies-mode"
                className="input select"
                value={copies === 'auto' ? 'auto' : 'custom'}
                onChange={(e) => update({ copies: e.target.value === 'auto' ? 'auto' : 1 })}
              >
                <option value="auto">Fill the sheet</option>
                <option value="custom">Exact number</option>
              </select>
              {copies !== 'auto' && (
                <input
                  id="psc-copies"
                  type="number"
                  className="input psc-copies-num"
                  min={1}
                  max={500}
                  value={copies}
                  onChange={(e) =>
                    update({ copies: Math.max(1, Math.min(500, parseInt(e.target.value, 10) || 1)) })
                  }
                  aria-label="Number of copies"
                />
              )}
            </div>
          </div>
        )}

        <div className="form-group">
          <label className="label" htmlFor="psc-gap">Gap <strong>{gapMm} mm</strong></label>
          <input
            id="psc-gap"
            type="range"
            className="range-slider"
            min={0}
            max={20}
            step={0.5}
            value={gapMm}
            onChange={(e) => update({ gapMm: parseFloat(e.target.value) })}
          />
        </div>

        <div className="form-group">
          <label className="label" htmlFor="psc-margin">Margin <strong>{marginMm} mm</strong></label>
          <input
            id="psc-margin"
            type="range"
            className="range-slider"
            min={0}
            max={25}
            step={0.5}
            value={marginMm}
            onChange={(e) => update({ marginMm: parseFloat(e.target.value) })}
          />
        </div>

        <div className="form-group psc-span">
          <label className="label" htmlFor="psc-perf">
            Cutter ring{' '}
            {perforationMm > 0 ? (
              <strong>+{perforationMm} mm → cut at {(diameterMm + perforationMm).toFixed(1)} mm</strong>
            ) : (
              <strong>off</strong>
            )}
          </label>
          <input
            id="psc-perf"
            type="range"
            className="range-slider"
            min={0}
            max={40}
            step={0.5}
            value={perforationMm}
            onChange={(e) => update({ perforationMm: parseFloat(e.target.value) })}
            aria-label="Cutter ring allowance in millimetres"
          />
          <p className="dc-hint psc-perf-hint">
            {perforationMm > 0 ? (
              <>
                Dashed circle showing the paper disc your press needs — wider than the
                badge so the rim folds around the shell. Different machines need
                different allowances; 12 mm suits most 58 mm presses.
              </>
            ) : (
              <>No cutter ring will be drawn.</>
            )}
          </p>
          <div className="psc-perf-presets">
            {[0, 8, 12, 16, 20].map((v) => (
              <button
                key={v}
                type="button"
                className={`dc-preset ${Math.abs(perforationMm - v) < 0.01 ? 'active' : ''}`}
                onClick={() => update({ perforationMm: v })}
              >
                {v === 0 ? 'Off' : `+${v}`}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="psc-toggles">
        <label className="psc-check">
          <input
            type="checkbox"
            checked={includeRuler}
            onChange={(e) => update({ includeRuler: e.target.checked })}
          />
          <span>
            Calibration ruler
            <small>Proves your printer did not rescale the page</small>
          </span>
        </label>
        <label className="psc-check">
          <input
            type="checkbox"
            checked={drawGuides}
            onChange={(e) => update({ drawGuides: e.target.checked })}
          />
          <span>
            Cut guides
            <small>Trim circle and centring crosshairs</small>
          </span>
        </label>
      </div>

      {bestFit.improved && (
        <div className="psc-fit-tip">
          <div>
            <strong>Fit {bestFit.capacity} per sheet</strong> instead of {bestFit.currentCapacity}
            <small>{bestFit.changes.join(' · ')}</small>
          </div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={applyBestFit}>
            Apply
          </button>
        </div>
      )}

      {layout.fits ? (
        <div className="psc-summary">
          <span className="badge badge-success">
            {totalToPrint} badge{totalToPrint === 1 ? '' : 's'} · {layout.cols} × {layout.rows} per sheet
          </span>
          {pages > 1 && <span className="badge badge-accent">{pages} sheets</span>}
          <span className="psc-paper-info">{pw.toFixed(1)} × {ph.toFixed(1)} mm</span>
        </div>
      ) : (
        <div className="error-banner" role="alert">⚠️ {layout.reason}</div>
      )}

      <svg
        className="psc-diagram"
        viewBox={`0 0 ${SVG_W} ${SVG_H}`}
        role="img"
        aria-label={
          layout.fits
            ? `Sheet preview: ${layout.cols} by ${layout.rows} badges`
            : 'Sheet preview: badge does not fit'
        }
      >
        <rect x="0" y="0" width={SVG_W} height={SVG_H} fill="#ffffff" rx="1" />
        <rect
          x={marginMm * k}
          y={marginMm * k}
          width={SVG_W - marginMm * k * 2}
          height={SVG_H - marginMm * k * 2}
          fill="none"
          stroke="#c9c9d4"
          strokeWidth="0.3"
          strokeDasharray="1.5 1"
        />
        {includeRuler && layout.fits && (
          <g>
            <line
              x1={(pw - 50) / 2 * k}
              y1={(marginMm + 5.6) * k}
              x2={((pw - 50) / 2 + 50) * k}
              y2={(marginMm + 5.6) * k}
              stroke="#444"
              strokeWidth="0.4"
            />
            <text
              x={SVG_W / 2}
              y={(marginMm + 3) * k}
              textAnchor="middle"
              fontSize="1.8"
              fill="#666"
            >
              50 mm calibration
            </text>
          </g>
        )}
        {dots.map((d, i) => (
          <g key={i}>
            <circle
              cx={d.cx}
              cy={d.cy}
              r={(diameterMm / 2) * k}
              fill={`hsla(${d.hue}, 75%, 62%, 0.30)`}
              stroke={`hsl(${d.hue}, 70%, 48%)`}
              strokeWidth="0.25"
            />
            {perforationMm > 0 && (
              <circle
                cx={d.cx}
                cy={d.cy}
                r={((diameterMm + perforationMm) / 2) * k}
                fill="none"
                stroke="#8a8a99"
                strokeWidth="0.3"
                strokeDasharray="1.2 1"
              />
            )}
          </g>
        ))}
        {!layout.fits && (
          <text x={SVG_W / 2} y={SVG_H / 2} textAnchor="middle" fontSize="5" fill="#c00">
            does not fit
          </text>
        )}
      </svg>
      <p className="dc-hint psc-scale-note">Diagram is to scale.</p>
    </div>
  );
}
