/**
 * Camera capture.
 *
 * The guide circle is the real badge boundary: capture centre-crops the video
 * to a square and the badge fills that square edge to edge, so the guide is
 * drawn at r=50 of a 100-unit viewBox. v1 drew it at r=40, quietly telling
 * users to frame 20% tighter than the badge actually crops.
 *
 * Stream lifecycle is ref-based. v1's cleanup closed over `stream` from the
 * first render (always null), so the webcam light stayed on after unmount and
 * every "restart" leaked another MediaStream.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import './CameraCapture.css';
import { useApp } from '../../store/AppContext';

export interface SnappedPhoto {
  id: string;
  url: string;
  file: File;
}

interface Props {
  onCapture?: (file: File) => void;
  onBatchCapture?: (files: File[]) => void;
  initialMode?: 'single' | 'batch';
}

type CameraState = 'starting' | 'ready' | 'denied' | 'unavailable';

/**
 * Smallest believable "real picture" fraction of a camera frame. Anything
 * below this is treated as a failed measurement rather than as padding.
 */
const MIN_CONTENT_FRACTION = 0.6;

export function CameraCapture({ onCapture, onBatchCapture, initialMode = 'single' }: Props) {
  const { state } = useApp();
  const { diameterMm } = state;

  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const snapsRef = useRef<SnappedPhoto[]>([]);

  const [camera, setCamera] = useState<CameraState>('starting');
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<'single' | 'batch'>(initialMode);
  const [snaps, setSnaps] = useState<SnappedPhoto[]>([]);
  const [flash, setFlash] = useState(false);
  const [busy, setBusy] = useState(false);
  const [mirrored, setMirrored] = useState(true);
  /**
   * Fraction of the frame that is actual picture, once any black padding the
   * camera baked in is discounted. 1 means the frame is all picture.
   */
  const [content, setContent] = useState<{ w: number; h: number }>({ w: 1, h: 1 });

  snapsRef.current = snaps;

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
  }, []);

  /**
   * Measure how much of the frame is real picture.
   *
   * Some webcams satisfy a resolution request by padding their native sensor
   * mode with black, and that padding is part of the pixel data — it survives
   * into the captured photo, so no amount of CSS can hide it. Scanning one
   * downscaled frame tells us what to trim, in both the preview and the
   * capture, whatever the driver did.
   */
  const measureContent = useCallback(() => {
    const video = videoRef.current;
    // A degenerate stream (some virtual cameras emit 2x2 placeholders) must
    // never drive this: there is nothing meaningful to measure.
    if (!video || video.videoWidth < 64 || video.videoHeight < 64) return;

    const W = 96;
    const H = Math.max(1, Math.round((video.videoHeight / video.videoWidth) * W));
    const c = document.createElement('canvas');
    c.width = W;
    c.height = H;
    const ctx = c.getContext('2d', { willReadFrequently: true });
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, W, H);

    let data: Uint8ClampedArray;
    try {
      data = ctx.getImageData(0, 0, W, H).data;
    } catch {
      return; // tainted canvas; leave the frame untrimmed
    }

    const DARK = 18; // below this on all channels counts as padding
    const isDarkRow = (y: number) => {
      for (let x = 0; x < W; x++) {
        const i = (y * W + x) * 4;
        if ((data[i] ?? 0) > DARK || (data[i + 1] ?? 0) > DARK || (data[i + 2] ?? 0) > DARK) {
          return false;
        }
      }
      return true;
    };
    const isDarkCol = (x: number) => {
      for (let y = 0; y < H; y++) {
        const i = (y * W + x) * 4;
        if ((data[i] ?? 0) > DARK || (data[i + 1] ?? 0) > DARK || (data[i + 2] ?? 0) > DARK) {
          return false;
        }
      }
      return true;
    };

    let top = 0;
    let bottom = H - 1;
    while (top < bottom && isDarkRow(top)) top++;
    while (bottom > top && isDarkRow(bottom)) bottom--;
    let left = 0;
    let right = W - 1;
    while (left < right && isDarkCol(left)) left++;
    while (right > left && isDarkCol(right)) right--;

    const h = (bottom - top + 1) / H;
    const w = (right - left + 1) / W;

    /*
     * Clamp hard in both directions.
     *
     * Below 0.97 there is something real to trim. Below MIN_CONTENT the
     * measurement is not believable — a dim room or a dark backdrop can make
     * most of a legitimate frame read as "padding", and acting on that would
     * zoom the preview into a handful of pixels. Real letterboxing never eats
     * much more than a third of a dimension, so anything more extreme is
     * treated as a failed measurement and ignored.
     */
    const usable = (f: number) => (f < 0.97 && f >= MIN_CONTENT_FRACTION ? f : 1);
    const next = { w: usable(w), h: usable(h) };
    setContent((prev) =>
      Math.abs(prev.w - next.w) < 0.01 && Math.abs(prev.h - next.h) < 0.01 ? prev : next,
    );
  }, []);

  const startCamera = useCallback(async () => {
    stopStream(); // never stack streams
    setError(null);
    setCamera('starting');

    if (!navigator.mediaDevices?.getUserMedia) {
      setCamera('unavailable');
      setError('This browser does not support camera access. You can upload a photo instead.');
      return;
    }

    try {
      // Ask only for a useful minimum and let the driver pick its native
      // mode. Forcing an exact 16:9 size makes some webcams satisfy the
      // request by padding their native sensor frame with black bars, which
      // then end up baked into the captured photo.
      const s = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 1280 } },
        audio: false,
      });
      streamRef.current = s;
      const video = videoRef.current;
      if (!video) {
        s.getTracks().forEach((t) => t.stop());
        return;
      }
      video.srcObject = s;
      await video.play().catch(() => undefined);
      setCamera('ready');
      // Give the sensor a moment to expose, then measure the real picture area.
      window.setTimeout(measureContent, 400);
      window.setTimeout(measureContent, 1200);
      // A camera unplugged or revoked mid-session must not look frozen.
      s.getVideoTracks().forEach((t) => {
        t.onended = () => {
          setCamera('unavailable');
          setError('The camera was disconnected.');
        };
      });
    } catch (err) {
      const name = err instanceof DOMException ? err.name : '';
      if (name === 'NotAllowedError' || name === 'SecurityError') {
        setCamera('denied');
        setError('Camera permission was denied. Allow access in your browser, or upload a photo instead.');
      } else if (name === 'NotFoundError' || name === 'OverconstrainedError') {
        setCamera('unavailable');
        setError('No camera was found on this device. You can upload a photo instead.');
      } else {
        setCamera('unavailable');
        setError('The camera could not be started. You can upload a photo instead.');
      }
    }
  }, [stopStream, measureContent]);

  useEffect(() => {
    void startCamera();
    return () => {
      stopStream();
      // Release any object URLs this component created.
      snapsRef.current.forEach((s) => URL.revokeObjectURL(s.url));
    };
    // startCamera/stopStream are stable; running once is intentional.
  }, [startCamera, stopStream]);

  /** Centre-crop the current video frame to a square JPEG, minus any padding. */
  const grabFrame = useCallback(async (): Promise<SnappedPhoto | null> => {
    const video = videoRef.current;
    if (!video || camera !== 'ready' || !video.videoWidth) return null;

    // Work inside the real picture area, not the padded frame.
    const srcW = video.videoWidth * content.w;
    const srcH = video.videoHeight * content.h;
    const size = Math.round(Math.min(srcW, srcH));
    if (size < 8) return null;

    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;

    // Mirror the capture too when the preview is mirrored, so what the user
    // lines up is what they get.
    if (mirrored) {
      ctx.translate(size, 0);
      ctx.scale(-1, 1);
    }
    ctx.drawImage(
      video,
      (video.videoWidth - size) / 2,
      (video.videoHeight - size) / 2,
      size,
      size,
      0,
      0,
      size,
      size,
    );

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', 0.95),
    );
    if (!blob) return null;

    const file = new File([blob], `snap_${Date.now()}.jpg`, { type: 'image/jpeg' });
    return {
      id: `snap-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      url: URL.createObjectURL(blob),
      file,
    };
  }, [camera, mirrored, content]);

  const handleSnap = useCallback(async () => {
    if (busy) return; // double-click guard: v1 created duplicate sessions
    setBusy(true);
    try {
      const frame = await grabFrame();
      if (!frame) {
        setError('Could not capture a frame. Try restarting the camera.');
        return;
      }
      setFlash(true);
      window.setTimeout(() => setFlash(false), 280);

      if (mode === 'single') {
        if (onCapture) onCapture(frame.file);
        else if (onBatchCapture) onBatchCapture([frame.file]);
        URL.revokeObjectURL(frame.url);
      } else {
        setSnaps((prev) => [...prev, frame]);
      }
    } finally {
      setBusy(false);
    }
  }, [busy, grabFrame, mode, onCapture, onBatchCapture]);

  const removeSnap = (id: string) => {
    setSnaps((prev) => {
      prev.filter((s) => s.id === id).forEach((s) => URL.revokeObjectURL(s.url));
      return prev.filter((s) => s.id !== id);
    });
  };

  const finishBatch = () => {
    if (snaps.length === 0) return;
    onBatchCapture?.(snaps.map((s) => s.file));
    snaps.forEach((s) => URL.revokeObjectURL(s.url));
    setSnaps([]);
  };

  const live = camera === 'ready';

  return (
    <div className="camera-wrap">
      <div className="camera-mode-pills" role="tablist" aria-label="Camera mode">
        <button
          type="button"
          id="cam-mode-single"
          role="tab"
          aria-selected={mode === 'single'}
          className={`camera-mode-pill ${mode === 'single' ? 'active' : ''}`}
          onClick={() => setMode('single')}
        >
          👤 One photo
        </button>
        <button
          type="button"
          id="cam-mode-batch"
          role="tab"
          aria-selected={mode === 'batch'}
          className={`camera-mode-pill ${mode === 'batch' ? 'active' : ''}`}
          onClick={() => setMode('batch')}
        >
          👥 Many photos
        </button>
      </div>

      {error && <div className="error-banner" role="alert">⚠️ {error}</div>}

      <div className="camera-viewport">
        {/*
          The padding is symmetric, so scaling about the centre by 1/smaller
          fraction pushes it outside the square while keeping the subject
          centred — the preview then shows exactly what the capture keeps.
        */}
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          onLoadedMetadata={measureContent}
          className={`camera-video ${mirrored ? 'mirrored' : ''}`}
          style={{
            // Belt and braces: even if a measurement slipped through, the
            // preview can never zoom more than 1.67x.
            ['--cam-trim' as string]: Math.min(
              1 / MIN_CONTENT_FRACTION,
              1 / Math.min(content.w, content.h),
            ),
          }}
        />

        {!live && (
          <div className="camera-placeholder">
            {camera === 'starting' ? (
              <><span className="spinner" /> Starting camera…</>
            ) : (
              <span>📷 Camera unavailable</span>
            )}
          </div>
        )}

        {flash && <div className="camera-flash-overlay" />}

        {/*
          viewBox is 100×100 over a square viewport, and capture crops that
          same square, so r=50 is exactly the badge edge.
        */}
        <svg className="camera-overlay" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          <defs>
            <mask id="badge-hole">
              <rect x="0" y="0" width="100" height="100" fill="white" />
              <circle cx="50" cy="50" r="50" fill="black" />
            </mask>
          </defs>
          {/* Dim everything the badge will crop away. */}
          <rect x="0" y="0" width="100" height="100" fill="rgba(0,0,0,0.55)" mask="url(#badge-hole)" />
          <circle
            cx="50"
            cy="50"
            r="49.5"
            fill="none"
            stroke="hsl(262,85%,75%)"
            strokeWidth="0.8"
            strokeDasharray="3 2"
          />
          <line x1="50" y1="42" x2="50" y2="58" stroke="rgba(255,255,255,0.45)" strokeWidth="0.4" />
          <line x1="42" y1="50" x2="58" y2="50" stroke="rgba(255,255,255,0.45)" strokeWidth="0.4" />
        </svg>

        <div className="camera-diam-label">
          Everything inside the circle becomes your {diameterMm.toFixed(0)} mm badge
        </div>
      </div>

      {mode === 'batch' && snaps.length > 0 && (
        <div className="camera-strip-wrap">
          <div className="camera-strip-header">
            <span>Captured ({snaps.length})</span>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => {
                snaps.forEach((s) => URL.revokeObjectURL(s.url));
                setSnaps([]);
              }}
            >
              Clear all
            </button>
          </div>
          <div className="camera-strip-scroll">
            {snaps.map((s, idx) => (
              <div key={s.id} className="camera-strip-item">
                <img src={s.url} alt={`Capture ${idx + 1}`} className="camera-strip-img" />
                <button
                  type="button"
                  className="camera-strip-del"
                  onClick={() => removeSnap(s.id)}
                  aria-label={`Remove capture ${idx + 1}`}
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="camera-actions">
        <button
          id="btn-capture"
          type="button"
          className="btn btn-primary btn-lg"
          onClick={() => void handleSnap()}
          disabled={!live || busy}
        >
          📸 {mode === 'single' ? 'Capture' : 'Add to batch'}
        </button>

        {mode === 'batch' && snaps.length > 0 && (
          <button
            id="btn-finish-batch"
            type="button"
            className="btn btn-accent btn-lg"
            onClick={finishBatch}
          >
            Use these {snaps.length} →
          </button>
        )}

        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => setMirrored((m) => !m)}
          title="Mirroring makes the preview feel like a mirror; the capture matches it either way"
        >
          {mirrored ? '🪞 Mirrored' : '🪞 Not mirrored'}
        </button>

        <button type="button" className="btn btn-ghost btn-sm" onClick={() => void startCamera()}>
          ↺ Restart camera
        </button>
      </div>

      <p className="camera-hint">
        {mode === 'single'
          ? 'Fill the circle with the subject, then capture.'
          : 'Capture each person in turn, then press "Use these" to add them all.'}
      </p>
    </div>
  );
}
