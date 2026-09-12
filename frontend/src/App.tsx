import { BrowserRouter, Routes, Route } from 'react-router-dom';
import './index.css';
import { AppProvider, useApp } from './store/AppContext';
import { HomePage } from './pages/HomePage';
import { EditorPage } from './pages/EditorPage';
import { PrintPage } from './pages/PrintPage';

function Navbar() {
  const { state } = useApp();
  const { step } = state;

  const steps: { key: typeof step; label: string; path: string }[] = [
    { key: 'input',  label: 'Photo',  path: '/' },
    { key: 'editor', label: 'Design', path: '/editor' },
    { key: 'print',  label: 'Print',  path: '/print' },
  ];

  const order = ['input', 'editor', 'print'];
  const currentIdx = order.indexOf(step);

  return (
    <nav className="navbar" role="navigation" aria-label="Main navigation">
      <div className="nav-inner">
        <span className="nav-logo">🔘 Button Buddy</span>
        <div className="nav-steps" role="list">
          {steps.map((s, i) => {
            const status =
              i < currentIdx ? 'done' :
              i === currentIdx ? 'active' : '';
            return (
              <div key={s.key} className="flex items-center gap-1" role="listitem">
                {i > 0 && <div className="step-line" />}
                <div className={`step-indicator ${status}`} aria-current={status === 'active' ? 'step' : undefined}>
                  <div className="step-dot">{status === 'done' ? '✓' : i + 1}</div>
                  <span className="step-label" style={{ fontSize: '0.78rem', fontWeight: 600 }}>{s.label}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </nav>
  );
}

function AppRoutes() {
  return (
    <>
      <Navbar />
      <main>
        <Routes>
          <Route path="/"       element={<HomePage />} />
          <Route path="/editor" element={<EditorPage />} />
          <Route path="/print"  element={<PrintPage />} />
        </Routes>
      </main>
    </>
  );
}

export default function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AppProvider>
  );
}
