/**
 * Export + print.
 *
 * The PDF is the accurate artefact — its geometry is in PostScript points and
 * cannot be rescaled by a browser print box. The browser print path is
 * supported but explicitly secondary: even with an exact `@page` size, the
 * user can still defeat it with "Fit to printable area" in the OS dialog.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';

import './PrintPreview.css';
import {
  assetUrl,
  downloadFile,
  exportPdf,
  exportPngSheet,
  toApiError,
  triggerBrowserDownload,
} from '../../api/client';
import type { ExportDto, ExportPayload } from '../../api/client';
import { useApp } from '../../store/AppContext';
import { isPrintable, isStale } from '../../store/types';
import { cellSizeMm, computeLayout, pageSizeCss } from '../../utils/paperLayouts';

export function PrintPreview() {
  const { state, dispatch } = useApp();
  const navigate = useNavigate();
  const { printConfig, diameterMm, bleedMm, badges } = state;
  const { paper, orientation, copies, gapMm, marginMm, includeRuler, drawGuides, perforationMm } =
    printConfig;

  const [sheet, setSheet] = useState<ExportDto | null>(null);
  const [pdf, setPdf] = useState<ExportDto | null>(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [busy, setBusy] = useState<'pdf' | 'png' | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const runRef = useRef<(kind: 'pdf' | 'png') => Promise<void>>(async () => {});

  useEffect(() => () => abortRef.current?.abort(), []);

  const printable = useMemo(
    () => badges.filter((b) => isPrintable(b, diameterMm, bleedMm)),
    [badges, diameterMm, bleedMm],
  );

  // The server refuses an impossible layout with a 400; the UI should never
  // offer it in the first place.
  const layout = computeLayout(
    paper,
    orientation,
    cellSizeMm(diameterMm, bleedMm, perforationMm),
    gapMm,
    marginMm,
    undefined,
    includeRuler ? undefined : 0,
  );
  const layoutFits = layout.fits;
  const staleCount = badges.filter(
    (b) => b.compositeUrl && isStale(b, diameterMm, bleedMm),
  ).length;
  const unrenderedCount = badges.filter((b) => !b.compositeUrl && b.status !== 'uploading').length;

  // Any change to geometry invalidates a generated sheet — showing the old one
  // beside new settings is exactly how someone prints the wrong thing.
  useEffect(() => {
    setSheet(null);
    setPdf(null);
    setPageIndex(0);
  }, [paper, orientation, copies, gapMm, marginMm, includeRuler, drawGuides, perforationMm, diameterMm, bleedMm, printable.length]);

  /*
   * Build the preview automatically.
   *
   * Seeing the real sheet is the point of this screen, so it should not be
   * behind a button. Debounced, because the effect above clears the sheet on
   * every settings change and dragging a slider would otherwise fire one
   * render per frame.
   */
  const autoRef = useRef<number | null>(null);
  useEffect(() => {
    if (sheet !== null || busy !== null || printable.length === 0 || !layoutFits) return;
    if (autoRef.current !== null) window.clearTimeout(autoRef.current);
    autoRef.current = window.setTimeout(() => void runRef.current('png'), 450);
    return () => {
      if (autoRef.current !== null) window.clearTimeout(autoRef.current);
    };
  }, [sheet, busy, printable.length, layoutFits]);

  const buildPayload = useCallback((): ExportPayload | null => {
    if (printable.length === 0) return null;
    const base: ExportPayload = {
      paper,
      orientation,
      gap_mm: gapMm,
      margin_mm: marginMm,
      include_ruler: includeRuler,
      draw_guides: drawGuides,
      perforation_mm: perforationMm,
      // The server rejects the export if this disagrees with what was
      // rendered, so the UI can never promise a size the PDF will not deliver.
      expect_diameter_mm: diameterMm,
    };
    if (printable.length === 1) {
      const only = printable[0];
      if (!only) return null;
      return {
        ...base,
        session_id: only.sessionId,
        copies: copies === 'auto' ? null : Number(copies),
      };
    }
    return {
      ...base,
      items: printable.map((b) => ({ session_id: b.sessionId, copies: b.copies || 1 })),
    };
  }, [printable, paper, orientation, gapMm, marginMm, includeRuler, drawGuides, perforationMm, diameterMm, copies]);

  const run = useCallback(
    async (kind: 'pdf' | 'png') => {
      const payload = buildPayload();
      if (!payload) return;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setBusy(kind);
      setError(null);
      try {
        const result =
          kind === 'pdf'
            ? await exportPdf(payload, controller.signal)
            : await exportPngSheet(payload, controller.signal);
        if (kind === 'pdf') setPdf(result);
        else {
          setSheet(result);
          setPageIndex(0);
        }
      } catch (err) {
        const e = toApiError(err);
        if (!e.isCancel) setError(e.message);
      } finally {
        setBusy(null);
        abortRef.current = null;
      }
    },
    [buildPayload],
  );

  // The auto-preview effect runs before `run` is defined; a ref keeps them
  // decoupled without reordering the whole component.
  runRef.current = run;

  /**
   * Print through the browser.
   *
   * `@page size` must be injected at print time because CSS cannot compute it
   * from a variable, and the sheet image must be sized in physical mm — not
   * `width: 100%`, which resolves against the printable area and silently
   * shrinks every badge by the printer's hardware margin.
   */
  const handlePrint = useCallback(() => {
    if (!sheet) return;
    const id = 'bb-print-page-rule';
    document.getElementById(id)?.remove();
    const style = document.createElement('style');
    style.id = id;
    const { w, h } = sheetDimsMm(paper, orientation);
    style.textContent = `
      @page { size: ${pageSizeCss(paper, orientation)}; margin: 0; }
      @media print {
        .pp-print-surface { width: ${w}mm !important; height: ${h}mm !important; }
        .pp-print-surface img { width: ${w}mm !important; height: ${h}mm !important; }
      }
    `;
    document.head.appendChild(style);
    window.print();
  }, [sheet, paper, orientation]);

  /**
   * Save a generated file.
   *
   * Prefers the server's attachment endpoint, where the filename comes from
   * Content-Disposition. A client-side `download` attribute is not reliable:
   * browsers ignore it alongside `target="_blank"`, and managed-browser
   * policies can ignore it entirely — producing an extensionless file named
   * after the blob UUID that the OS then refuses to open.
   */
  const saveFile = useCallback(
    async (dto: ExportDto, index: number, fallbackName: string) => {
      setDownloading(true);
      setError(null);
      try {
        const attachment = dto.download_urls?.[index];
        if (attachment) {
          triggerBrowserDownload(assetUrl(attachment));
        } else {
          const raw = dto.urls[index];
          if (raw) await downloadFile(raw, fallbackName);
        }
      } catch (err) {
        setError(toApiError(err).message);
      } finally {
        setDownloading(false);
      }
    },
    [],
  );

  const handleDownload = useCallback(() => {
    if (!pdf) return;
    void saveFile(pdf, 0, `button-buddy-${diameterMm.toFixed(0)}mm-${paper}-${orientation}.pdf`);
  }, [pdf, saveFile, diameterMm, paper, orientation]);

  const canExport = printable.length > 0 && busy === null && layoutFits;
  const pageUrl = sheet?.urls[pageIndex];

  return (
    <div className="print-preview">
      {(staleCount > 0 || unrenderedCount > 0) && (
        <div className="warn-banner" role="status">
          <div className="warn-banner-text">
            ⚠️{' '}
            {staleCount > 0 && (
              <>
                {staleCount} badge{staleCount === 1 ? ' was' : 's were'} rendered at a different
                size and {staleCount === 1 ? 'is' : 'are'} excluded.{' '}
              </>
            )}
            {unrenderedCount > 0 && (
              <>
                {unrenderedCount} badge{unrenderedCount === 1 ? ' has' : 's have'} not been rendered
                yet.{' '}
              </>
            )}
            Go to the editor to render with applied settings and include them.
          </div>
          <button
            type="button"
            className="btn btn-primary btn-sm warn-banner-btn"
            onClick={() => {
              dispatch({ type: 'SET_STEP', payload: 'editor' });
              navigate('/editor');
            }}
          >
            ✦ Go to render →
          </button>
        </div>
      )}

      <div className="pp-actions">
        <button
          id="btn-gen-pdf"
          type="button"
          className="btn btn-accent btn-lg"
          onClick={() => void run('pdf')}
          disabled={!canExport}
        >
          {busy === 'pdf' ? <><span className="spinner" /> Building PDF…</> : '📄 Create print-ready PDF'}
        </button>

        <button
          id="btn-gen-sheet"
          type="button"
          className="btn btn-secondary"
          onClick={() => void run('png')}
          disabled={!canExport}
        >
          {busy === 'png' ? <><span className="spinner" /> Rendering…</> : '🖼 Preview the sheet'}
        </button>
      </div>

      {!layout.fits && printable.length > 0 && (
        <div className="error-banner" role="alert">⚠️ {layout.reason}</div>
      )}

      {printable.length === 0 && (
        <div className="pp-placeholder card">
          <div className="drop-icon">📄</div>
          <h3>Nothing ready to print yet</h3>
          <p>Render at least one badge in the editor, then come back here.</p>
        </div>
      )}

      {error && <div className="error-banner" role="alert">⚠️ {error}</div>}

      {pdf && (
        <div className="pp-pdf-ready">
          <div>
            <strong className="pp-ready-title">
              ✓ PDF ready — {pdf.badges_placed} badge{pdf.badges_placed === 1 ? '' : 's'} across{' '}
              {pdf.total_pages} page{pdf.total_pages === 1 ? '' : 's'}
            </strong>
            <p className="pp-ready-sub">
              Every circle is exactly <strong>{pdf.diameter_mm.toFixed(1)} mm</strong>.
              {pdf.truncated && ' Some badges were dropped to stay within the page limit.'}
            </p>
          </div>
          <div className="pp-ready-actions">
            <button
              id="btn-download-pdf"
              type="button"
              className="btn btn-accent"
              onClick={() => void handleDownload()}
              disabled={downloading}
            >
              {downloading ? <><span className="spinner" /> Saving…</> : '⬇ Download PDF'}
            </button>
            <button
              id="btn-open-pdf"
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => window.open(assetUrl(pdf.urls[0] ?? ''), '_blank', 'noopener')}
            >
              Open in new tab
            </button>
          </div>
        </div>
      )}

      <div className="pp-calibration card">
        <h4>Printing at the right size</h4>
        <ol>
          <li>
            Open the PDF and set scale to <strong>100% / Actual size</strong>. Never
            "Fit to page" — that is what makes badges come out undersized.
          </li>
          <li>
            Measure the <strong>50 mm calibration bar</strong> at the top of the sheet with a
            ruler. If it reads 50 mm, every badge is exact.
          </li>
          <li>Use the quadrant ticks around each circle to centre your punch cutter.</li>
        </ol>
      </div>

      {sheet && pageUrl && (
        <div className="pp-sheet-wrap">
          <div className="pp-sheet-header">
            <span className="label">
              Sheet preview · 300 DPI · {sheet.layout.cols} × {sheet.layout.rows}
            </span>
            {sheet.total_pages > 1 && (
              <div className="pp-pager">
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => setPageIndex((i) => Math.max(0, i - 1))}
                  disabled={pageIndex === 0}
                >
                  ‹
                </button>
                <span>Page {pageIndex + 1} of {sheet.total_pages}</span>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => setPageIndex((i) => Math.min(sheet.total_pages - 1, i + 1))}
                  disabled={pageIndex >= sheet.total_pages - 1}
                >
                  ›
                </button>
              </div>
            )}
            <button
              id="btn-save-sheet"
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() =>
                void saveFile(
                  sheet,
                  pageIndex,
                  `button-buddy-${diameterMm.toFixed(0)}mm-${paper}-${orientation}.png`,
                )
              }
              disabled={downloading}
              title="Save this sheet as a 300 DPI PNG"
            >
              ⬇ Save image
            </button>
            <button
              id="btn-browser-print"
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={handlePrint}
            >
              🖨 Print this page
            </button>
          </div>

          <div className="pp-sheet-container">
            <img src={assetUrl(pageUrl)} alt={`Print sheet page ${pageIndex + 1}`} className="pp-sheet-img" />
          </div>

          <p className="dc-hint pp-print-note">
            Browser printing depends on your print dialog. For guaranteed size, use the PDF.
          </p>
        </div>
      )}

      {/*
        Portalled to <body> so the print stylesheet can hide every other
        top-level node with a simple `body > *:not(...)` rule. Nested inside
        the app it would inherit transforms, overflow and padding from
        ancestors, any one of which can shift or clip the sheet on paper.
      */}
      {sheet && pageUrl &&
        createPortal(
          <div className="pp-print-surface" aria-hidden="true">
            <img src={assetUrl(pageUrl)} alt="" />
          </div>,
          document.body,
        )}
    </div>
  );
}

function sheetDimsMm(paper: string, orientation: string): { w: number; h: number } {
  const sizes: Record<string, { w: number; h: number }> = {
    A4: { w: 210, h: 297 },
    A3: { w: 297, h: 420 },
    Letter: { w: 215.9, h: 279.4 },
    Legal: { w: 215.9, h: 355.6 },
    '4x6': { w: 101.6, h: 152.4 },
  };
  const base = sizes[paper] ?? sizes.A4!;
  return orientation === 'portrait' ? base : { w: base.h, h: base.w };
}
