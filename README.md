# Button Buddy 🔘

**Button Buddy** is a precision web application designed for creating, framing, batching, and printing pinback button badges with 100% physical accuracy on paper.

It features a WYSIWYG interactive circular canvas, automatic multi-photo batching via camera or file upload, built-in branding frames, and vector PDF export with hairline cutting guides, quadrant crosshairs, and a 50.0 mm calibration ruler.

---

## ✨ Key Features

- **Guaranteed Physical Print Accuracy**: Badges (e.g., standard 58.0 mm) print at the exact millimeter size specified when printed at 100% / Actual Size.
- **1:1 WYSIWYG Alignment**: What you see in the canvas preview matches the rendered badge pixel-for-pixel (pan, zoom, and framing).
- **Multi-Paper Support**: Full layout engine supporting **A4**, **A3**, **Letter**, **Legal**, and **4" × 6" (101.6 × 152.4 mm)** photo paper.
- **Batch Processing & Camera Support**:
  - Upload multiple photos or capture continuous shots via webcam.
  - Per-badge copy steppers and individual rendering status chips.
  - Quick **"Go to render"** navigation and one-click **"⚡ Render with applied settings"**.
- **Vector PDF & 300 DPI Export**:
  - Clean vector cutting circles and outer perforation bleed rings.
  - Quadrant crosshairs (2.5 mm outward ticks) for alignment with acrylic punch cutters.
  - Embedded 50.0 mm physical calibration test ruler to verify printer scaling before cutting.

---

## 📋 Prerequisites

Before running the project locally, ensure you have installed:
- **Python 3.10+** (Python 3.11+ recommended)
- **Node.js 18+** & **npm 9+**
- **Git**

---

## 🚀 How to Initialize and Run Locally

Follow these steps to clone, configure, and launch both the backend and frontend servers locally.

### 1. Clone the Repository

```bash
git clone https://github.com/tumul901/button-buddy-app-cpxp.git
cd button-buddy-app-cpxp
```

---

### 2. Backend Setup (FastAPI)

The backend manages image composition (Pillow), SQLite storage (SQLModel), template branding, and precision vector PDF generation (ReportLab).

1. **Navigate to the backend directory:**
   ```bash
   cd backend
   ```

2. **Create and activate a virtual environment:**
   - **Windows (PowerShell):**
     ```powershell
     python -m venv .venv
     .venv\Scripts\Activate.ps1
     ```
   - **Windows (Command Prompt):**
     ```cmd
     python -m venv .venv
     .venv\Scripts\activate.bat
     ```
   - **macOS / Linux:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables:**
   Copy the provided example file:
   - **Windows:** `copy .env.example .env`
   - **macOS / Linux:** `cp .env.example .env`

5. **Start the local backend server:**
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
   > 💡 *On first startup, the server automatically initializes SQLite (`buttonbuddy.db`) and seeds the default badge templates.*
   - **API URL**: [http://localhost:8000](http://localhost:8000)
   - **Interactive API Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

### 3. Frontend Setup (React + TypeScript + Vite)

The frontend provides the interactive framing canvas, camera capture, batch tray, and sheet print preview.

1. **Open a new terminal window and navigate to the frontend directory:**
   ```bash
   cd frontend
   ```

2. **Install npm dependencies:**
   ```bash
   npm install
   ```

3. **Set up environment variables:**
   Copy the example environment file:
   - **Windows:** `copy .env.example .env`
   - **macOS / Linux:** `cp .env.example .env`
   *(By default, requests are routed through Vite's built-in dev proxy to `http://localhost:8000`)*

4. **Start the frontend development server:**
   ```bash
   npm run dev
   ```

5. **Open the application:**
   Navigate to [http://localhost:5173](http://localhost:5173) (or the port indicated in your console, e.g., `http://localhost:5175`).

---

## 🛠️ Verification & Calibration

### Physical Paper Print Verification
1. Design your badge or batch of badges in the editor.
2. Go to the **Print** page and select your paper size (e.g. `4" × 6"` or `A4`).
3. Click **📄 Create print-ready PDF**.
4. When printing from Adobe Acrobat or your browser print dialog:
   - **Crucial**: Ensure scale is set to **"Actual Size"** or **100%** (do **NOT** use *"Fit to page"* or *"Shrink to printable area"*).
5. Use a physical ruler to measure the **50.0 mm calibration bar** on the printed paper:
   - If the bar measures exactly 50 mm, your button diameter is guaranteed to be 100% accurate (e.g. 58.0 mm).

### Running Tests
- **Backend Tests:**
  ```bash
  cd backend
  pytest
  ```
- **Frontend Typecheck & Production Build:**
  ```bash
  cd frontend
  npm run build
  ```

---

## 📂 Project Structure

```text
button-buddy/
├── backend/
│   ├── app/
│   │   ├── models/            # SQLModel database schemas (BadgeTemplate, etc.)
│   │   ├── routers/           # API endpoints (render, export, templates, sessions)
│   │   ├── schemas/           # Pydantic request/response schemas
│   │   └── services/          # Compositor (Pillow) & PDF exporter (ReportLab)
│   ├── seed_templates.py      # Template generation script
│   ├── requirements.txt       # Python dependencies
│   └── .env.example           # Backend environment template
├── frontend/
│   ├── src/
│   │   ├── components/        # TemplateEditor, BadgeTray, CameraCapture, PrintPreview
│   │   ├── store/             # AppContext and state management
│   │   ├── utils/             # Paper layout engine and math utilities
│   │   └── pages/             # HomePage, EditorPage, PrintPage
│   ├── package.json           # Frontend dependencies
│   └── vite.config.ts         # Vite configuration with backend proxy
└── README.md
```

---

## 📄 License

MIT License. Designed with care for makers, badge pressers, and creative studios.
