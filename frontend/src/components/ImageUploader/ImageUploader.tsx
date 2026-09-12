/**
 * Drop zone.
 *
 * Files are handed straight to the shared upload action, which owns
 * validation — no FileReader here at all. v1 read every file to a data URL
 * first, with no `onerror` handler, so one unreadable file left `Promise.all`
 * pending forever and the UI stuck on a spinner that no refresh-free path
 * could clear.
 */

import { useRef, useState } from 'react';

import './ImageUploader.css';
import { MAX_FILE_MB } from '../../hooks/useBadgeActions';

interface Props {
  onFiles: (files: File[]) => void;
  busy?: boolean;
}

export function ImageUploader({ onFiles, busy = false }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  const [dragging, setDragging] = useState(false);

  const submit = (list: FileList | File[] | null) => {
    if (!list || list.length === 0) return;
    onFiles(Array.from(list));
  };

  const openPicker = () => inputRef.current?.click();

  return (
    <div className="uploader-wrap">
      <div
        className={`drop-zone ${dragging ? 'drag-over' : ''} ${busy ? 'is-busy' : ''}`}
        // dragenter/leave fire for every child element; counting depth stops
        // the highlight flickering as the cursor crosses inner nodes.
        onDragEnter={(e) => {
          e.preventDefault();
          dragDepth.current += 1;
          setDragging(true);
        }}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={() => {
          dragDepth.current -= 1;
          if (dragDepth.current <= 0) {
            dragDepth.current = 0;
            setDragging(false);
          }
        }}
        onDrop={(e) => {
          e.preventDefault();
          dragDepth.current = 0;
          setDragging(false);
          submit(e.dataTransfer.files);
        }}
        onClick={openPicker}
        role="button"
        tabIndex={0}
        aria-label="Add photos"
        aria-disabled={busy}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            openPicker();
          }
        }}
      >
        <div className="drop-icon">{dragging ? '📥' : '📁'}</div>
        <p className="drop-title">{dragging ? 'Drop to add' : 'Drop photos here'}</p>
        <p className="drop-sub">or click to browse — one photo or many</p>
        <span className="badge badge-primary">JPEG · PNG · WebP · up to {MAX_FILE_MB} MB each</span>
      </div>

      <input
        ref={inputRef}
        type="file"
        multiple
        accept="image/jpeg,image/png,image/webp"
        style={{ display: 'none' }}
        onChange={(e) => {
          submit(e.target.files);
          // Reset so picking the same file twice still fires a change event.
          e.target.value = '';
        }}
      />
    </div>
  );
}
