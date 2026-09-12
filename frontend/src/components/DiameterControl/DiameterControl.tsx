/**
 * Badge size control.
 *
 * Offers the standard button-press sizes as presets, because a badge press
 * only accepts the die it was built for — a free-form 61.3 mm badge is not
 * something anyone can actually manufacture. The slider stays for the rare
 * custom die.
 */

import { useEffect, useState } from 'react';

import './DiameterControl.css';
import { useApp } from '../../store/AppContext';
import { isStale } from '../../store/types';
import { computeLayout } from '../../utils/paperLayouts';
import { mmToPx } from '../../utils/mmToPx';

const MIN_MM = 20;
const MAX_MM = 150;
const STEP_MM = 0.5;

/** Die sizes real badge presses ship with. */
const PRESETS = [25, 32, 38, 44, 58, 75] as const;

export function DiameterControl() {
  const { state, dispatch } = useApp();
  const { diameterMm, bleedMm, printConfig, badges } = state;
  const [text, setText] = useState(String(diameterMm));

  useEffect(() => setText(String(diameterMm)), [diameterMm]);

  const commit = (value: number) => {
    if (Number.isNaN(value)) {
      setText(String(diameterMm));
      return;
    }
    const clamped = Math.min(MAX_MM, Math.max(MIN_MM, value));
    dispatch({ type: 'SET_DIAMETER', payload: clamped });
  };

  const layout = computeLayout(
    printConfig.paper,
    printConfig.orientation,
    diameterMm + bleedMm * 2,
    printConfig.gapMm,
    printConfig.marginMm,
    undefined,
    printConfig.includeRuler ? undefined : 0,
  );

  // Warn before the user discovers it on the print page.
  const willInvalidate = badges.some(
    (b) => b.compositeUrl && isStale(b, diameterMm, bleedMm),
  );

  return (
    <div className="diameter-control card-raised">
      <div className="dc-header">
        <span className="label">Badge size</span>
        <span className="badge badge-primary">{mmToPx(diameterMm)} px @ 300 DPI</span>
      </div>

      <div className="dc-presets" role="group" aria-label="Standard badge sizes">
        {PRESETS.map((p) => (
          <button
            key={p}
            type="button"
            className={`dc-preset ${Math.abs(diameterMm - p) < 0.01 ? 'active' : ''}`}
            onClick={() => commit(p)}
            aria-pressed={Math.abs(diameterMm - p) < 0.01}
          >
            {p}<span className="dc-preset-unit">mm</span>
          </button>
        ))}
      </div>

      <div className="dc-row">
        <input
          id="diameter-slider"
          type="range"
          className="range-slider"
          min={MIN_MM}
          max={MAX_MM}
          step={STEP_MM}
          value={diameterMm}
          onChange={(e) => commit(parseFloat(e.target.value))}
          aria-label="Badge diameter in millimetres"
        />
        <div className="dc-input-wrap">
          <input
            id="diameter-number"
            type="number"
            className="input dc-number"
            min={MIN_MM}
            max={MAX_MM}
            step={STEP_MM}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              const v = parseFloat(e.target.value);
              if (!Number.isNaN(v) && v >= MIN_MM && v <= MAX_MM) {
                dispatch({ type: 'SET_DIAMETER', payload: v });
              }
            }}
            onBlur={() => commit(parseFloat(text))}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commit(parseFloat(text));
            }}
            aria-label="Badge diameter value"
          />
          <span className="dc-unit">mm</span>
        </div>
      </div>

      <p className="dc-hint">
        {layout.fits ? (
          <>
            <strong>{layout.capacityPerPage}</strong> per {printConfig.paper} sheet
            {' '}({layout.cols} × {layout.rows})
          </>
        ) : (
          <span className="dc-warn">⚠️ Does not fit on {printConfig.paper} — {layout.reason}</span>
        )}
      </p>

      {willInvalidate && (
        <p className="dc-warn dc-hint">
          ⚠️ Some badges were rendered at a different size. Render them again before printing.
        </p>
      )}
    </div>
  );
}
