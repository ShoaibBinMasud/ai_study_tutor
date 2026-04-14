import { useRef, useState } from "react";
import { uploadFiles } from "../api";

interface FileUploadProps {
  onUploaded: (welcomeText: string) => void;
  onError: (msg: string) => void;
  disabled: boolean;
}

export default function FileUpload({ onUploaded, onError, disabled }: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setLoading(true);
    try {
      const result = await uploadFiles(Array.from(files));
      onUploaded(result.text);
    } catch (e: unknown) {
      onError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    handleFiles(e.dataTransfer.files);
  }

  return (
    <div
      className={`upload-zone ${dragOver ? "drag-over" : ""} ${disabled || loading ? "disabled" : ""}`}
      onClick={() => !disabled && !loading && inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".pdf,.txt,.md,.pptx,.docx,.png,.jpg"
        style={{ display: "none" }}
        onChange={(e) => handleFiles(e.target.files)}
      />
      {loading ? (
        <span className="upload-loading">Reading materials...</span>
      ) : (
        <>
          <span className="upload-icon">📄</span>
          <span className="upload-label">Drop files or click to upload</span>
          <span className="upload-hint">PDF, PPTX, DOCX, images</span>
        </>
      )}
    </div>
  );
}
