import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

import './PrintPage.css';
import { BadgeTray } from '../components/BadgeTray/BadgeTray';
import { PrintPreview } from '../components/PrintPreview/PrintPreview';
import { PrintSheetConfig } from '../components/PrintSheetConfig/PrintSheetConfig';
import { useApp } from '../store/AppContext';

export function PrintPage() {
  const { state } = useApp();
  const navigate = useNavigate();

  // Only redirect once state has been restored, so a refresh on /print keeps
  // the user where they were instead of throwing away their work.
  useEffect(() => {
    if (state.hydrated && state.badges.length === 0) navigate('/', { replace: true });
  }, [state.hydrated, state.badges.length, navigate]);

  return (
    <div className="print-page fade-in-up">
      <div className="pp-tray-wrap">
        <BadgeTray />
      </div>

      <div className="pp-sidebar">
        <h2>Print</h2>
        <p className="ep-sub">
          Choose the paper and layout, then export. The PDF is the accurate one.
        </p>

        <PrintSheetConfig />

        <button className="btn btn-ghost btn-sm" onClick={() => navigate('/editor')}>
          ← Back to design
        </button>
      </div>

      <div className="pp-main">
        <PrintPreview />
      </div>
    </div>
  );
}
