# Button Buddy — Robustness Review & Remediation

**Audited:** 2026-09-12 (v1)
**Remediated:** 2026-09-12 (v1.1)
**Scope:** `backend/` + `frontend/`, against `implementation_plan.md`.

The original audit found **7 P0 blockers, 11 P1 correctness defects, 13 P2
resilience/security gaps and 11 P3 polish items**. This document now records
both the findings and what was done about them.

**Status: all P0 and P1 items fixed and verified; P2/P3 substantially done.**
The remaining open items are listed at the bottom with reasons.

---

## Verified outcomes

These are measurements, not assertions. Each was produced by running the code.

| Guarantee | Evidence |
|---|---|
| **A badge prints at exactly its stated size** | 12 badges measured out of a generated A4 PDF: every one **58.0000 mm**, worst error **0.0000 mm** |
| **Page geometry is exact** | PDF MediaBox **210.000 × 297.000 mm** for A4; verified for A3, Letter, Legal, 4×6, both orientations |
| **Browser printing is now accurate too** | Chrome's own print output measured **58.0259 mm** (error **+0.026 mm**, from Chrome's page rounding). Before the fix this path produced ~92–96% of the requested size |
| **What you frame is what prints** | Preview and 300 DPI render place the photo centre at **34.4749%** of badge width — identical to 4 dp across a 3.125× scale difference |
| **Nothing is placed off-page** | Bounds-checked across every paper × orientation × diameter × gap × margin combination |
| **Sheet capacity is correct** | Letter @58 mm/10 mm gap: **9 badges** (v1 said 6 — a third of the sheet wasted) |
| **Front and back agree on layout** | 450-case parity test compiles the real TypeScript module and compares against Python; proven to fail when either drifts |
| **Test suite** | **57 backend tests**, all passing |
| **Full user journey** | 14-step browser walkthrough: 0 problems, 0 console errors |

Reproduce with:

```bash
cd backend && .venv/Scripts/python -m pytest tests/ -q
python tools/measure_pdf.py <any-generated-sheet.pdf>
```

---

# P0 — Blockers (all fixed)

### P0-1. Browser print path ignored physical size ✅
`index.css` had `@page { size: auto }` and `width: 100%`, which resolves against
the **printable area** — excluding the printer's 4–6 mm hardware margins. Every
browser-printed badge came out ~92–96% of the requested size, and a leftover
`max-height: 600px` clamped the sheet on paper.

**Fixed:** the print surface is portalled to `<body>` (so no ancestor transform,
overflow or padding can shift it), `@page size` is injected per paper choice at
print time, and the sheet is sized in real mm with `max-height: none`. Measured
at **58.0259 mm**. The PDF is now clearly presented as the accurate path, and
the UI says so.

### P0-2. Backend could not boot from a clean checkout ✅
`StaticFiles(directory=...)` probes the path in `__init__` and raises; the
directory was only created later, in `lifespan`.
**Fixed:** directories are created at module scope, before the mount.

### P0-3. Docker Compose backend could not start ✅
Compose set a Postgres `DATABASE_URL` with no driver installed.
**Fixed:** `psycopg[binary]` added; all dependencies pinned to the versions the
project is verified against.

### P0-4. All work was lost on refresh ✅
State lived only in `useReducer` — one refresh destroyed a whole batch, which is
brutal for the event/kiosk case this app is for.
**Fixed:** debounced `localStorage` persistence with rehydration on mount, and
route guards that wait for hydration before redirecting. Photos are now stored
as server URLs rather than data URLs, so the persisted blob is small.
**Verified:** refresh on `/print` keeps the user on `/print` with badges intact.

### P0-5. Multi-badge export silently used the wrong diameter ✅
`diameter_mm` was reassigned inside the loop, so every badge on the sheet was
drawn at whatever the *last* session happened to be — the one failure mode this
product must never have.
**Fixed:** mixed diameters (and mixed bleed) are rejected with an explicit 409
naming the sizes involved. Additionally the client sends `expect_diameter_mm`
and the server refuses any export that disagrees with what was rendered.

### P0-6. Badges were placed off the page ✅
`max(1, int(usable/step))` claimed one column fits even when it did not — a
100 mm badge ran 8.4 mm off a 4×6 page, silently clipped.
**Fixed:** `compute_layout` returns `fits: false` with a human-readable reason;
the exporters refuse, and the UI disables export and shows the reason.

### P0-7. Empty template table was a dead end ✅
Rendering required a template, so a fresh database trapped the user in the
editor with a permanently disabled button.
**Fixed:** templates are optional end-to-end, "No frame" is a first-class
choice, and built-ins seed automatically on first boot.

---

# P1 — Correctness (all fixed)

| # | Defect | Resolution |
|---|---|---|
| P1-1 | Capacity formula charged a trailing gap to the last badge in each row — Letter@10 mm reported 6 where 9 fit | `floor((usable + gap) / (d + gap))` in both implementations, pinned by a parity test |
| P1-2 | Calibration ruler printed over the first badge row at margins below 10 mm | The ruler occupies a reserved 12 mm band that `compute_layout` subtracts from usable height; asserted at margins 0/5/8/10/15 |
| P1-3 | Ruler tick labels were 0.85 mm tall on paper — unreadable | Scalable font sized in print pixels, text centred by measured bbox instead of a hardcoded offset |
| P1-4 | Preview disagreed with the render whenever bleed > 0 | The preview box is now the full artwork footprint (trim + 2 × bleed); the trim circle is an inset overlay |
| P1-5 | Crop offsets were raw CSS pixels with a hardcoded 96 DPI assumption | Offsets are normalised fractions of badge diameter — resolution-, zoom- and layout-independent |
| P1-6 | Non-square templates were stretched by the backend but cropped by the preview | Both use cover-fit; template alpha is clipped to the badge circle |
| P1-7 | Camera guide circle was 80% of the actual crop, so subjects framed 20% too tight | Guide is now the true badge boundary (r=50 of a 100 viewBox), with the cropped-away area dimmed |
| P1-12 | Black bars in the camera preview **and in the captured photo** (reported during testing) | Two causes addressed — see below |
| P1-8 | Changing diameter after rendering printed the old size while the UI promised the new one | `isStale()` marks affected badges, the editor shows a warning, the print step is blocked, and the server double-checks via `expect_diameter_mm` |
| P1-9 | PNG sheet silently dropped overflow while the PDF paginated | Both paginate; the PNG returns one file per page with a pager in the UI |
| P1-10 | "Auto (fill sheet)" silently did nothing in multi-badge mode | The control is hidden when the tray's per-badge copy counts govern, and shown when it applies |
| P1-11 | Stale images from fixed filenames; `Date.now()` re-fetched the sheet on every render | Composite URLs carry a server-issued `?v=<render_version>`; no ad-hoc cache-busting anywhere |

---

### P1-12 in detail — black bars baked into camera frames

Reported from a real webcam: black bars top and bottom in the preview **and in
the captured photo**. The second half is the diagnostic — CSS cannot reach
into captured pixel data, so this was never a layout problem. Measuring the
live DOM confirmed the viewport was a correct `520 × 520` with
`object-fit: cover`, which fills by definition.

The cause was over-constraining the stream:

```js
video: { facingMode: 'user', width: { ideal: 1920 }, height: { ideal: 1080 } }
```

Many webcams have a 4:3-native sensor. Some drivers satisfy a forced 16:9
request by **padding the native frame with black** rather than cropping, and
that padding is real pixel data.

Two fixes, because either alone leaves a gap:

1. **Ask for less.** `{ facingMode: 'user', width: { ideal: 1280 } }` — no
   height, no aspect ratio, so the driver returns its native mode unpadded.
2. **Trim whatever still arrives.** `measureContent()` samples one downscaled
   frame, finds uniformly-black edge rows/columns, and reports the real
   picture fraction. The preview scales past it (`--cam-trim`) and the capture
   crops to the same region, so preview and capture stay identical.

**A bug in the first version of this fix, caught by measuring rather than
eyeballing:** against a degenerate 2×2 virtual camera the detector concluded
1/96 of the frame was picture and applied a **96× zoom** — the video's layout
box stayed 518 px while its rendered box became 49728 px. `overflow: hidden`
meant a screenshot still looked plausible. Now clamped at both ends: streams
under 64 px are not measured at all, and a content fraction below 0.6 is
treated as a failed measurement, with the zoom additionally capped at 1.67×
where it is applied. On a normal camera the trim is exactly `1` — a true no-op.

*Not yet confirmed on the reporter's specific hardware:* Chromium's fake device
cannot reproduce the padding, so what is verified is that detection runs, the
geometry stays square, and nothing regressed.

---

# P2 — Resilience & security (fixed)

| # | Gap | Resolution |
|---|---|---|
| P2-1 | Webcam stream never stopped — cleanup closed over `null`; every restart leaked a stream | Ref-based lifecycle, stop-before-start, `track.onended` handling, explicit permission-denied / no-camera states |
| P2-2 | A failed `FileReader` hung the UI forever (no `onerror`, `Promise.all` never settled) | `FileReader` removed entirely; files go straight to the upload action |
| P2-3 | `MAX_FILE_SIZE` was declared and never used; `content_type` was trusted | Byte cap enforced **while streaming** (413), every file decoded and verified by Pillow before it is persisted. **Verified:** 25 MB upload → 413 |
| P2-4 | Client-controlled file extension written into a statically-served directory (stored XSS) | Extension comes from the **detected** format; `X-Content-Type-Options: nosniff` on uploads. **Verified:** HTML bytes → 400; a real PNG named `.html` → stored as `photo.png` |
| P2-5 | `POST /templates` was unauthenticated | Gated behind `ADMIN_TOKEN` when set; `DELETE` added |
| P2-6 | A failed template upload left a row whose empty path 500-ed the whole listing | Files are written and validated before the row is committed; the listing skips and logs bad rows instead of failing |
| P2-7 | Filesystem paths stored in the database | Storage-relative keys with traversal-safe resolution; response models keep internals out of the API |
| P2-8 | No migrations; `create_all` never alters an existing table | A startup schema guard detects an older database, archives it non-destructively (SQLite) or refuses to start with instructions (Postgres). **This fired for real during remediation and worked.** |
| P2-9 | Full-resolution photos held in memory as base64 data URLs | Photos are server URLs; object URLs are used only transiently and revoked |
| P2-10 | Batch operations serial, uncancellable, and abandoned on first failure | Bounded concurrency (3), per-badge status, `AbortController` cancel, per-item retry, and a summary of what failed |
| P2-11 | No logging, no error handling, health check lied | Structured logging, request IDs, global exception handler with a correlation reference, and a health check that actually probes the database and uploads directory |
| P2-12 | `strict` absent from tsconfig; API layer returned `any` | `strict` + `noUncheckedIndexedAccess` enabled, every response typed, errors normalised through `toApiError`. Typecheck is clean |
| P2-13 | No tests at all | **57 backend tests**: print accuracy measured out of real PDFs, layout capacity, bounds, ruler clearance, crop clamping, EXIF rotation, and cross-language parity |

Also fixed along the way: session TTL sweep (photos no longer accumulate
indefinitely), timezone-aware timestamps, SQLite WAL so concurrent renders do
not hit "database is locked", env-driven CORS, and same-origin dev requests
through the Vite proxy so CORS stops being a failure mode at all.

---

# P3 — Polish (fixed)

Template list no longer refetches on every selection · one shared `PaperSize`
definition · copy counts bounded in the UI to match the server · `ImageReader`
reused so a 12-up sheet decodes the image once instead of twelve times · unused
props removed · positions computed from unrounded mm so no drift accumulates
across a row · camera preview mirrored (and capture mirrored to match) ·
double-submit guards on capture and render · horizontal overflow eliminated at
390 px.

---

# Still open

| Item | Why it is still open |
|---|---|
| **Alembic migrations** | The startup guard makes the failure safe and legible, but a real migration tool is the correct long-term answer. Needed before there is production data worth preserving. |
| **Production Docker targets** | Both Dockerfiles are still dev-only (`--reload`, `vite dev`). A production build (static frontend + uvicorn workers) is separate work. |
| **Not a git repository** | `backend/.env`, `buttonbuddy.db`, `uploads/**` and `.venv/` are all untracked in a non-repo. `git init` plus a `.gitignore` is worth doing before further changes. |
| **Frontend unit tests** | Backend coverage is good and the parity test executes the real frontend layout module, but there is no Vitest suite for components. |
| **Physical print test** | Everything is verified digitally, to 0.026 mm. **One actual sheet should still be printed and measured with a ruler** — that is what the calibration bar is for, and it is the only check that covers your specific printer and driver. |

---

# Architectural notes worth keeping

**The crop contract.** Offsets are fractions of the badge diameter, not pixels.
This is why the preview can be any size — responsive, zoomed, high-DPI — and
still match the 300 DPI render exactly. Any future change to the editor must
preserve this; the proof is that the photo centre lands at the same percentage
in a 219 px preview and a 685 px render.

**Two implementations of one layout.** `layout.py` and `paperLayouts.ts` exist
separately so sliders feel instant without a round trip. They *will* drift —
the parity test in `tests/test_layout.py` compiles the real TypeScript and
compares 450 cases, and it has been verified to fail when either side changes.

**PDF over browser print.** Both are accurate now, but only the PDF is immune to
the user's print dialog. "Fit to printable area" is on by default in most
dialogs and silently shrinks output; the 50 mm calibration bar exists so that
mistake is visible on paper rather than discovered after cutting 200 badges.
