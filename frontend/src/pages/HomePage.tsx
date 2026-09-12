import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import './HomePage.css';
import { CameraCapture } from '../components/CameraCapture/CameraCapture';
import { DiameterControl } from '../components/DiameterControl/DiameterControl';
import { ImageUploader } from '../components/ImageUploader/ImageUploader';
import { useApp } from '../store/AppContext';
import { useBadgeActions } from '../hooks/useBadgeActions';

type InputMode = 'upload' | 'camera' | null;

export function HomePage() {
  const { state, dispatch } = useApp();
  const navigate = useNavigate();
  const { addPhotos } = useBadgeActions();
  const [mode, setMode] = useState<InputMode>(null);

  const handleFiles = async (files: File[]) => {
    const added = await addPhotos(files);
    if (added.length > 0) {
      dispatch({ type: 'SET_STEP', payload: 'editor' });
      navigate('/editor');
    }
  };

  const resume = () => {
    dispatch({ type: 'SET_STEP', payload: 'editor' });
    navigate('/editor');
  };

  return (
    <div className="home-page fade-in-up">
      <section className="hero">
        <span className="badge badge-accent">Badge maker</span>
        <h1>
          Print badges at <span className="gradient-text">exactly</span> the right size
        </h1>
        <p className="hero-sub">
          Add photos, frame them, and get a print-ready sheet where every circle measures
          precisely {state.diameterMm.toFixed(0)} mm on paper.
        </p>
        <DiameterControl />
      </section>

      {state.badges.length > 0 && (
        <div className="home-resume card">
          <span>
            You have <strong>{state.badges.length}</strong> badge
            {state.badges.length === 1 ? '' : 's'} in progress.
          </span>
          <button type="button" className="btn btn-primary btn-sm" onClick={resume}>
            Continue →
          </button>
        </div>
      )}

      {!mode && (
        <div className="input-cards">
          <button
            id="btn-upload-mode"
            type="button"
            className="input-card card"
            onClick={() => setMode('upload')}
          >
            <span className="ic-icon">📁</span>
            <h3>Upload photos</h3>
            <p>Pick one or many images from this device</p>
          </button>

          <button
            id="btn-camera-mode"
            type="button"
            className="input-card card"
            onClick={() => setMode('camera')}
          >
            <span className="ic-icon">📷</span>
            <h3>Use the camera</h3>
            <p>Snap people one at a time, or a whole queue</p>
          </button>
        </div>
      )}

      {mode && (
        <div className="input-panel card">
          <div className="ip-header">
            <h3>{mode === 'upload' ? 'Upload photos' : 'Camera'}</h3>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setMode(null)}>
              ✕ Cancel
            </button>
          </div>

          {mode === 'upload' && (
            <ImageUploader onFiles={(f) => void handleFiles(f)} busy={state.isBusy} />
          )}
          {mode === 'camera' && (
            <CameraCapture
              onCapture={(file) => void handleFiles([file])}
              onBatchCapture={(files) => void handleFiles(files)}
            />
          )}
        </div>
      )}

      {state.error && <div className="error-banner" role="alert">⚠️ {state.error}</div>}
    </div>
  );
}
