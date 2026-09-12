# Button Buddy — Complete Implementation Plan

> **This document is the single source of truth. Every file, API endpoint, data model, and UI component needed to build the entire app is defined here.**

---

## Why 25.4?

**25.4 is the exact number of millimetres in one inch** — defined by the International System of Units (SI) as an exact conversion:

```
1 inch = 25.4 mm  (exact, by international agreement since 1959)
```

Screens and printers use **DPI (dots per inch)** — not dots per millimetre. So to convert a physical measurement in mm into pixels or print dots, we must cross from the metric system into the inch-based DPI system:

```
pixels = mm × (DPI / 25.4)
```

Breaking this down:
- `mm / 25.4` → converts millimetres to inches
- `inches × DPI` → converts inches to pixels/dots at the target resolution

**Example — 58 mm badge at 300 DPI:**
```
pixels = 58 × (300 / 25.4)
       = 58 × 11.8110...
       = 685.04  →  round to 685 px
```

We chose **300 DPI** because:
- It is the industry-standard minimum for photo-quality print
- Badge printers and laser printers operate at 300–600 DPI
- Below 300 DPI, circles appear jagged when cut by a badge press
- At 96 DPI (screen default), a 58 mm badge would only be ~219 px — far too coarse for print

**Why `@media print` enforces the physical size:**
- We generate the canvas at 685 × 685 px (print resolution)
- In the print stylesheet we set `width: 58mm; height: 58mm` on the image element
- The browser's print engine then maps exactly 685 px → 58 mm on paper
- This works because the browser knows the printer's actual DPI at print time
- We never hardcode screen DPI — we only hardcode print canvas DPI (300) and let CSS handle the rest

```
Formula locked in:
  PRINT_DPI = 300
  canvasSizePx = Math.round(diameterMm * PRINT_DPI / 25.4)
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     BROWSER (React + Vite)                      │
│  HomePage → EditorPage → PrintPage                              │
│  Canvas API  |  CSS mm units  |  @media print                   │
└──────────────────────┬──────────────────────────────────────────┘
                       │ REST (JSON + multipart)
┌──────────────────────▼──────────────────────────────────────────┐
│               FastAPI (Python 3.12)                             │
│  /templates  |  /sessions  |  /render  |  /export-pdf           │
│  Pillow (image compositing)  |  ReportLab (PDF generation)      │
└──────────────────────┬──────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────────┐
│  PostgreSQL (sessions, templates)  +  Local disk / S3 (assets)  │
└─────────────────────────────────────────────────────────────────┘
```

### Why a mandatory backend?

| Concern | Frontend-only limit | Backend solution |
|---|---|---|
| PDF generation with exact physical mm sizing | Browser PDF unreliable across OS/printer drivers | ReportLab generates PDF with guaranteed mm dimensions |
| Template management (PNG/JPG branding assets) | Assets must be bundled at build time | FastAPI serves templates dynamically; new templates added without redeploy |
| High-res compositing (>20 MP images) | Browser canvas silently clamps large canvases on mobile | Pillow on server handles any resolution |
| Session persistence | Refreshing loses all work | Session stored server-side; shareable link |
| Multi-badge sheet rendering | Canvas tiling complex in browser | Server renders complete sheet as single high-res PNG/PDF |

---

## Tech Stack (Final)

| Layer | Technology | Version |
|---|---|---|
| Frontend framework | React + TypeScript | React 18, Vite 5 |
| Styling | Vanilla CSS + CSS custom properties | — |
| Routing | React Router | v6 |
| HTTP client | Axios | v1 |
| Backend framework | FastAPI | 0.111 |
| Python runtime | Python | 3.12 |
| Image processing | Pillow | 10.x |
| PDF generation | ReportLab | 4.x |
| Database | PostgreSQL | 16 |
| ORM | SQLModel | 0.0.18 |
| Containerisation | Docker + Docker Compose | — |
| File storage | Local `/uploads` volume (swap to S3 in prod) | — |
| Font (UI) | Inter (Google Fonts) | — |

---

## Repository Structure

```
button-buddy/
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── api/
│   │   │   └── client.ts              # Axios instance + typed API calls
│   │   ├── components/
│   │   │   ├── DiameterControl/
│   │   │   │   ├── DiameterControl.tsx
│   │   │   │   └── DiameterControl.css
│   │   │   ├── CameraCapture/
│   │   │   │   ├── CameraCapture.tsx
│   │   │   │   └── CameraCapture.css
│   │   │   ├── ImageUploader/
│   │   │   │   ├── ImageUploader.tsx
│   │   │   │   └── ImageUploader.css
│   │   │   ├── TemplateSelector/
│   │   │   │   ├── TemplateSelector.tsx
│   │   │   │   └── TemplateSelector.css
│   │   │   ├── TemplateEditor/
│   │   │   │   ├── TemplateEditor.tsx  # Canvas compositor
│   │   │   │   └── TemplateEditor.css
│   │   │   ├── PrintSheetConfig/
│   │   │   │   ├── PrintSheetConfig.tsx
│   │   │   │   └── PrintSheetConfig.css
│   │   │   └── PrintPreview/
│   │   │       ├── PrintPreview.tsx
│   │   │       └── PrintPreview.css
│   │   ├── hooks/
│   │   │   ├── useCamera.ts
│   │   │   ├── useComposite.ts
│   │   │   └── usePrintSheet.ts
│   │   ├── pages/
│   │   │   ├── HomePage.tsx
│   │   │   ├── EditorPage.tsx
│   │   │   └── PrintPage.tsx
│   │   ├── store/
│   │   │   ├── AppContext.tsx          # React Context + useReducer
│   │   │   └── types.ts               # All shared TS types
│   │   ├── utils/
│   │   │   ├── mmToPx.ts
│   │   │   ├── paperLayouts.ts        # A4, Letter, A3 tiling math
│   │   │   └── canvasUtils.ts
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css
│   ├── index.html
│   ├── vite.config.ts
│   └── package.json
│
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app entry
│   │   ├── config.py                  # Settings (env vars)
│   │   ├── database.py                # SQLModel engine
│   │   ├── models/
│   │   │   ├── template.py            # Template DB model
│   │   │   └── session.py             # BadgeSession DB model
│   │   ├── routers/
│   │   │   ├── templates.py           # GET /templates, POST /templates
│   │   │   ├── sessions.py            # POST /sessions, GET /sessions/{id}
│   │   │   ├── render.py              # POST /render (composite image)
│   │   │   └── export.py              # POST /export/pdf, POST /export/png-sheet
│   │   ├── services/
│   │   │   ├── compositor.py          # Pillow compositing logic
│   │   │   ├── layout.py              # Sheet tiling math (Python mirror of frontend)
│   │   │   └── pdf_exporter.py        # ReportLab PDF builder
│   │   └── schemas/
│   │       ├── render_request.py
│   │       └── export_request.py
│   ├── uploads/                       # Persisted user photos + templates
│   ├── requirements.txt
│   └── Dockerfile
│
├── docker-compose.yml
└── README.md
```

---

## Frontend — Detailed Component Specification

### `src/utils/mmToPx.ts`

```ts
/** 1 inch = 25.4 mm exactly (SI definition).
 *  Printers use DPI (dots-per-inch), not dots-per-mm.
 *  To get print pixels: convert mm → inches → dots.
 */
export const PRINT_DPI = 300;

export function mmToPx(mm: number, dpi: number = PRINT_DPI): number {
  return Math.round(mm * (dpi / 25.4));
}

export function pxToMm(px: number, dpi: number = PRINT_DPI): number {
  return (px / dpi) * 25.4;
}
```

---

### `src/utils/paperLayouts.ts`

Defines all supported paper sizes and computes badge tiling.

```ts
export type PaperSize = 'A4' | 'A3' | 'Letter' | 'Legal';

export const PAPER_SIZES_MM: Record<PaperSize, { w: number; h: number }> = {
  A4:     { w: 210, h: 297 },
  A3:     { w: 297, h: 420 },
  Letter: { w: 215.9, h: 279.4 },
  Legal:  { w: 215.9, h: 355.6 },
};

export interface SheetLayout {
  cols: number;
  rows: number;
  totalBadges: number;
  paperMm: { w: number; h: number };
  badgeDiameterMm: number;
  gapMm: number;
  marginMm: number;
}

export function computeLayout(
  paper: PaperSize,
  diameterMm: number,
  gapMm: number,      // space between badge edges
  marginMm: number,   // page margin
  copies?: number,    // if set, override auto-fill
): SheetLayout {
  const p = PAPER_SIZES_MM[paper];
  const step = diameterMm + gapMm;
  const usableW = p.w - marginMm * 2;
  const usableH = p.h - marginMm * 2;
  const cols = Math.floor(usableW / step);
  const rows = Math.floor(usableH / step);
  return {
    cols,
    rows,
    totalBadges: copies ?? cols * rows,
    paperMm: p,
    badgeDiameterMm: diameterMm,
    gapMm,
    marginMm,
  };
}
```

---

### `src/store/types.ts`

All application state types in one place:

```ts
export interface AppState {
  step: 'input' | 'editor' | 'print';
  diameterMm: number;          // user-controlled, default 58
  bleedMm: number;             // default 3
  rawImageDataUrl: string | null;
  selectedTemplateId: string | null;
  compositeDataUrl: string | null;   // result from /render
  sessionId: string | null;
  printConfig: PrintConfig;
}

export interface PrintConfig {
  paper: PaperSize;
  copies: number | 'auto';    // 'auto' = fill the page
  gapMm: number;              // default 5
  marginMm: number;           // default 10
}

export interface BadgeTemplate {
  id: string;
  name: string;
  thumbnailUrl: string;
  fullUrl: string;
  category: string;
}
```

---

### `src/components/DiameterControl/DiameterControl.tsx`

- Range slider: **25 mm → 100 mm**, step **0.5 mm**
- Numeric input with `mm` label (user can type exact value)
- Both inputs two-way bound
- Debounced 300 ms on slider to avoid re-render flood
- Shows computed print canvas size in px as helper text: `"685 × 685 px @ 300 DPI"`
- Shows how many badges fit on selected paper (live)

---

### `src/components/CameraCapture/CameraCapture.tsx`

**Camera overlay geometry:**

```
┌──────────────────────────────────────────┐
│              camera preview              │
│                                          │
│      ┌────────────────────┐              │
│      │   square guide     │              │
│      │  ╔══════════════╗  │  ← crosshair │
│      │  ║  - - - - -   ║  │              │
│      │  ║ (   circle  )║  │  ← dashed    │
│      │  ║  - - - - -   ║  │    circle    │
│      │  ╚══════════════╝  │              │
│      └────────────────────┘              │
│                                          │
│       [Capture]    Diameter: [58mm ▼]    │
└──────────────────────────────────────────┘
```

Implementation notes:
- `<video>` fills container, `object-fit: cover`
- SVG overlay positioned absolute, `pointer-events: none`
- Square = 80% of `min(videoWidth, videoHeight)` in px, then converted display via `mm` mental model
- Dashed circle: `<circle stroke-dasharray="8 4" />` inscribed in the square
- **The dashed circle's CSS diameter is NOT fixed to 58mm on screen** — it is just a visual guide. The actual physical size is determined at render/print time.
- Crosshair: two `<line>` elements through center of square
- Capture → `drawImage(video, ...)` on offscreen canvas → `canvas.toDataURL('image/jpeg', 0.95)` → passed to editor

---

### `src/components/ImageUploader/ImageUploader.tsx`

- Drag-and-drop zone with animated dashed border (CSS animation)
- Click to open file picker: `accept="image/jpeg,image/png,image/webp"`
- Max file size: 20 MB (client-side guard; backend also validates)
- On file select: read as DataURL → dispatch to store → navigate to editor

---

### `src/components/TemplateSelector/TemplateSelector.tsx`

- Fetches `GET /api/templates` on mount
- Renders grid of thumbnail cards (PNG/JPG previews)
- Selected template highlighted with ring border
- Templates are PNG/JPG files with transparent ring areas where the branding sits
- Selecting a template stores `selectedTemplateId` in state

---

### `src/components/TemplateEditor/TemplateEditor.tsx`

This is the core interactive compositor:

1. Shows a **screen-resolution preview canvas** (sized via CSS mm: `{diameterMm}mm`)
2. User can **pan and pinch-to-zoom** the photo within the circle
3. Template branding overlay drawn on top (fetched from backend, not re-editable)
4. "Render" button → calls `POST /api/render` with photo + template + crop params
5. Backend returns composite PNG at print resolution (685 px for 58 mm)
6. Frontend shows the result; user can go to Print or go back

Pan/zoom state:
```ts
interface CropState {
  offsetX: number; // px within the original image
  offsetY: number; // px
  scale: number;   // zoom factor, min 1.0
}
```

---

### `src/components/PrintSheetConfig/PrintSheetConfig.tsx`

User controls the print sheet layout:

| Control | Options |
|---|---|
| Paper size | A4 / A3 / Letter / Legal |
| Copies | `Auto (fill page)` or numeric input 1–100 |
| Gap between badges | Slider 2–20 mm |
| Page margin | Slider 5–25 mm |
| Orientation | Portrait / Landscape (swaps W and H) |

Live preview shows a tiny diagram of the sheet with badge circles placed on it (SVG, not canvas).

---

### `src/components/PrintPreview/PrintPreview.tsx`

- Calls `POST /api/export/png-sheet` with layout config + session ID
- Backend returns a single high-res PNG of the full sheet
- Frontend shows it in an `<img>` tag
- In `@media print`: hide everything, show only the `<img>` with explicit paper CSS:

```css
@media print {
  @page { size: A4 portrait; margin: 0; }
  body * { display: none; }
  .print-sheet-img {
    display: block !important;
    width: 210mm;
    height: 297mm;
  }
}
```

- Print button: `window.print()`
- Download PDF button: calls `POST /api/export/pdf`

---

## Backend — Detailed API Specification

Base URL: `http://localhost:8000/api`

### `GET /api/templates`

Returns list of all available branding templates.

**Response:**
```json
[
  {
    "id": "uuid",
    "name": "Classic Red",
    "category": "sport",
    "thumbnail_url": "/uploads/templates/classic_red_thumb.jpg",
    "full_url": "/uploads/templates/classic_red.png"
  }
]
```

### `POST /api/templates` *(admin)*

Upload a new template PNG/JPG.

**Request:** `multipart/form-data`
- `file`: PNG or JPG image (must be square, transparent ring area for branding)
- `name`: string
- `category`: string

**Response:** Template object

---

### `POST /api/sessions`

Create a new badge session (stores user photo + config).

**Request:** `multipart/form-data`
- `photo`: image file
- `diameter_mm`: float (default 58)
- `bleed_mm`: float (default 3)
- `template_id`: string

**Response:**
```json
{
  "session_id": "uuid",
  "photo_url": "/uploads/sessions/{id}/photo.jpg"
}
```

---

### `POST /api/render`

Composite the photo + template into a print-resolution circle PNG.

**Request JSON:**
```json
{
  "session_id": "uuid",
  "template_id": "uuid",
  "diameter_mm": 58.0,
  "bleed_mm": 3.0,
  "crop": {
    "offset_x": 0.0,
    "offset_y": 0.0,
    "scale": 1.2
  }
}
```

**Backend logic (Pillow):**
1. `canvas_px = round(diameter_mm * 300 / 25.4)` → e.g. 685
2. `bleed_px = round(bleed_mm * 300 / 25.4)` → e.g. 35
3. `total_px = canvas_px + bleed_px * 2` → 755
4. Open user photo → apply crop/scale transform
5. Paste photo onto 755×755 canvas, apply circular mask (inner 685 px)
6. Open template PNG → resize to 755×755 → composite over photo (alpha blending)
7. Draw red bleed circle guide at radius 377 px, 1 px stroke
8. Save as PNG to `/uploads/sessions/{id}/composite.png`

**Response:**
```json
{
  "composite_url": "/uploads/sessions/{id}/composite.png",
  "canvas_px": 685,
  "total_with_bleed_px": 755
}
```

---

### `POST /api/export/png-sheet`

Render a complete print sheet with badges tiled on it.

**Request JSON:**
```json
{
  "session_id": "uuid",
  "paper": "A4",
  "orientation": "portrait",
  "copies": "auto",
  "gap_mm": 5.0,
  "margin_mm": 10.0
}
```

**Backend logic:**
1. Mirror `computeLayout()` in Python
2. Create blank white canvas at paper size @ 300 DPI:
   - A4 portrait: `round(210 * 300/25.4)` × `round(297 * 300/25.4)` = 2480 × 3508 px
3. Tile badge PNG (composite) into computed grid positions
4. Save as PNG

**Response:**
```json
{
  "sheet_url": "/uploads/sessions/{id}/sheet_A4.png",
  "layout": { "cols": 3, "rows": 4, "total_badges": 12 }
}
```

---

### `POST /api/export/pdf`

Generate a PDF with guaranteed physical mm dimensions.

**Request JSON:** Same as `png-sheet`

**Backend logic (ReportLab):**
1. Compute layout identical to png-sheet
2. Create PDF canvas at paper size (ReportLab uses points: 1 pt = 1/72 inch)
   - `width_pt = paper_w_mm / 25.4 * 72`
3. For each badge position: `drawImage(composite_path, x_pt, y_pt, width=badge_w_pt, height=badge_h_pt)`
4. ReportLab handles DPI scaling internally

**Why PDF guarantees physical size:**
- PDF standard stores dimensions in points (1/72 inch)
- `58 mm = 58/25.4 × 72 = 164.4 pt` — exact, printer-agnostic
- No dependency on OS print dialog or browser print margins

**Response:**
```json
{
  "pdf_url": "/uploads/sessions/{id}/sheet_A4.pdf"
}
```

---

## Database Schema

### `templates` table

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| name | VARCHAR(100) | |
| category | VARCHAR(50) | |
| file_path | VARCHAR(500) | path on disk |
| thumbnail_path | VARCHAR(500) | |
| created_at | TIMESTAMP | |

### `badge_sessions` table

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| photo_path | VARCHAR(500) | |
| composite_path | VARCHAR(500) | nullable until rendered |
| template_id | UUID FK → templates | |
| diameter_mm | FLOAT | default 58 |
| bleed_mm | FLOAT | default 3 |
| crop_offset_x | FLOAT | |
| crop_offset_y | FLOAT | |
| crop_scale | FLOAT | |
| print_config | JSONB | paper, copies, gap, margin |
| created_at | TIMESTAMP | |

---

## `services/compositor.py` — Core Logic

```python
from PIL import Image, ImageDraw
import math

PRINT_DPI = 300

def mm_to_px(mm: float) -> int:
    """
    1 inch = 25.4 mm (SI exact definition).
    Printers use DPI (dots-per-inch).
    px = mm / 25.4 * DPI
    """
    return round(mm * PRINT_DPI / 25.4)

def composite_badge(
    photo_path: str,
    template_path: str,
    diameter_mm: float,
    bleed_mm: float,
    crop_offset_x: float,
    crop_offset_y: float,
    crop_scale: float,
    output_path: str,
) -> dict:
    badge_px = mm_to_px(diameter_mm)
    bleed_px = mm_to_px(bleed_mm)
    total_px = badge_px + bleed_px * 2

    # --- 1. Prepare photo ---
    photo = Image.open(photo_path).convert("RGBA")
    # Apply scale
    scaled_w = int(photo.width * crop_scale)
    scaled_h = int(photo.height * crop_scale)
    photo = photo.resize((scaled_w, scaled_h), Image.LANCZOS)
    # Apply crop offset (center within total_px canvas)
    photo_canvas = Image.new("RGBA", (total_px, total_px), (255, 255, 255, 255))
    paste_x = (total_px - scaled_w) // 2 + int(crop_offset_x)
    paste_y = (total_px - scaled_h) // 2 + int(crop_offset_y)
    photo_canvas.paste(photo, (paste_x, paste_y))

    # --- 2. Circular mask (inner badge, no bleed) ---
    mask = Image.new("L", (total_px, total_px), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse(
        [bleed_px, bleed_px, bleed_px + badge_px, bleed_px + badge_px],
        fill=255
    )
    photo_canvas.putalpha(mask)

    # --- 3. Composite template over photo ---
    template = Image.open(template_path).convert("RGBA").resize(
        (total_px, total_px), Image.LANCZOS
    )
    result = Image.alpha_composite(photo_canvas, template)

    # --- 4. Draw bleed guide circle ---
    guide_draw = ImageDraw.Draw(result)
    guide_draw.ellipse(
        [1, 1, total_px - 1, total_px - 1],
        outline=(255, 0, 0, 180),
        width=2
    )

    result.save(output_path, "PNG", dpi=(PRINT_DPI, PRINT_DPI))
    return {"badge_px": badge_px, "bleed_px": bleed_px, "total_px": total_px}
```

---

## `services/layout.py` — Sheet Tiling

```python
PAPER_SIZES_MM = {
    "A4":     {"w": 210,   "h": 297},
    "A3":     {"w": 297,   "h": 420},
    "Letter": {"w": 215.9, "h": 279.4},
    "Legal":  {"w": 215.9, "h": 355.6},
}

def compute_layout(paper, diameter_mm, gap_mm, margin_mm, orientation="portrait"):
    p = PAPER_SIZES_MM[paper].copy()
    if orientation == "landscape":
        p["w"], p["h"] = p["h"], p["w"]
    usable_w = p["w"] - margin_mm * 2
    usable_h = p["h"] - margin_mm * 2
    step = diameter_mm + gap_mm
    cols = int(usable_w / step)
    rows = int(usable_h / step)
    return {"cols": cols, "rows": rows, "total": cols * rows, "paper_mm": p}
```

---

## Docker Compose

```yaml
version: "3.9"
services:
  frontend:
    build: ./frontend
    ports: ["5173:5173"]
    volumes: ["./frontend:/app"]
    command: npm run dev -- --host

  backend:
    build: ./backend
    ports: ["8000:8000"]
    volumes:
      - ./backend:/app
      - uploads_data:/app/uploads
    environment:
      - DATABASE_URL=postgresql://bb:bb@db:5432/buttonbuddy
    depends_on: [db]

  db:
    image: postgres:16
    environment:
      POSTGRES_USER: bb
      POSTGRES_PASSWORD: bb
      POSTGRES_DB: buttonbuddy
    volumes: [pg_data:/var/lib/postgresql/data]
    ports: ["5432:5432"]

volumes:
  uploads_data:
  pg_data:
```

---

## Complete User Flow (Step by Step)

```
1. User lands on HomePage
   ├── Sees diameter control (default 58 mm)
   │    └── Helper text: "685 × 685 px @ 300 DPI | 12 badges fit on A4"
   └── Chooses:
       ├── [Upload Photo] → ImageUploader → file picked
       └── [Use Camera]  → CameraCapture → frame captured

2. Photo sent to POST /api/sessions → session_id returned

3. EditorPage loads
   ├── TemplateSelector: fetches GET /api/templates → user picks one
   ├── TemplateEditor: shows live preview canvas
   │    ├── User pans/zooms photo within circle
   │    └── [Render] → POST /api/render → composite PNG returned
   └── User can adjust diameter → re-renders automatically

4. PrintPage loads
   ├── PrintSheetConfig: user sets paper, copies, gap, margin, orientation
   ├── [Generate Sheet] → POST /api/export/png-sheet → sheet PNG returned
   ├── Preview shown in browser
   ├── [Print] → window.print() uses @media print CSS
   └── [Download PDF] → POST /api/export/pdf → PDF downloaded
```

---

## Styling System (`src/index.css`)

```css
:root {
  --color-primary:    hsl(262, 80%, 58%);
  --color-accent:     hsl(340, 85%, 60%);
  --color-bg:         hsl(240, 12%, 8%);
  --color-surface:    hsl(240, 10%, 13%);
  --color-border:     hsl(240, 8%, 22%);
  --color-text:       hsl(240, 10%, 94%);
  --color-text-muted: hsl(240, 8%, 60%);
  --radius-sm:  6px;
  --radius-md: 12px;
  --radius-lg: 20px;
  --shadow-glow: 0 0 30px hsla(262, 80%, 58%, 0.25);
}

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Inter', sans-serif; background: var(--color-bg); color: var(--color-text); }
```

---

## Verification Plan

### Unit Tests (Vitest — frontend)
```bash
npx vitest run
```
- `mmToPx(58)` → `685`
- `mmToPx(0)` → `0`
- `mmToPx(25.4)` → `300` (exactly 1 inch at 300 DPI)
- `computeLayout('A4', 58, 5, 10)` → `{ cols: 3, rows: 4, total: 12 }`
- `computeLayout('Letter', 58, 5, 10)` → correct col/row count

### Unit Tests (pytest — backend)
```bash
pytest backend/tests/
```
- `mm_to_px(58)` == 685
- `compute_layout("A4", 58, 5, 10)["total"]` == 12
- `composite_badge(...)` produces PNG of correct pixel size
- PDF export sets page size within 0.1 pt of expected

### Print Accuracy Test (Manual)
1. Set diameter to **58 mm**, print to PDF
2. Open PDF in Adobe Reader → measure circle with measuring tool
3. Expected: **58.0 mm ± 0.5 mm**
4. Physical test: print on paper → measure with ruler

---

## Phased Rollout

| Phase | Deliverables |
|---|---|
| **MVP (Week 1–2)** | Upload + Camera, single template, render, window.print() |
| **v1.1 (Week 3)** | Template gallery, pan/zoom, print sheet config, PNG sheet export |
| **v1.2 (Week 4)** | PDF export via ReportLab, A3/Letter/Legal paper, orientation toggle |
| **v2.0 (Future)** | Admin template upload UI, session sharing via link, order batching |
