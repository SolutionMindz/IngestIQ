import { useCallback, useState, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import type { DocumentSummary, DocumentVersion } from '../../types/document';
import type { ScreenshotItem } from '../../api/client';
import { fetchVersionHistory, simulateUpload, fetchScreenshots, screenshotUrl, cancelDocumentJob } from '../../api';

interface DocumentIntakeProps {
  document: DocumentSummary | null;
  onUploadComplete: (doc: DocumentSummary) => void;
}

const STAGE_LABELS: Record<DocumentSummary['processingStage'], string> = {
  pending: 'Pending',
  extracting: 'Extracting',
  comparing: 'Comparing',
  done: 'Done',
  error: 'Error',
  cancelled: 'Cancelled',
};

const IN_PROGRESS_STAGES: DocumentSummary['processingStage'][] = ['pending', 'extracting', 'comparing'];

function isInProgress(stage: DocumentSummary['processingStage']): boolean {
  return IN_PROGRESS_STAGES.includes(stage);
}

const VALIDATION_LABELS: Record<string, string> = {
  pending: 'Pending',
  structurally_verified: 'Structurally Verified',
  integrity_conflict: 'Integrity Conflict',
  training_approved: 'Training Approved',
  screenshot_failed: 'Screenshot Failed',
  validation_failed: 'Validation Failed',
};

export default function DocumentIntake({ document, onUploadComplete }: DocumentIntakeProps) {
  const [uploading, setUploading] = useState(false);
  const [versions, setVersions] = useState<DocumentVersion[]>([]);
  const [versionsLoaded, setVersionsLoaded] = useState(false);
  const [screenshots, setScreenshots] = useState<ScreenshotItem[]>([]);
  const [screenshotsLoading, setScreenshotsLoading] = useState(false);
  const [selectedPage, setSelectedPage] = useState<number | null>(null);
  const [modalPage, setModalPage] = useState<number | null>(null);
  const [hoverPage, setHoverPage] = useState<number | null>(null);
  const [cancelling, setCancelling] = useState(false);

  const handleCancelJob = useCallback(() => {
    if (!document?.documentId || !isInProgress(document.processingStage)) return;
    setCancelling(true);
    cancelDocumentJob(document.documentId)
      .then((updated) => {
        onUploadComplete(updated);
      })
      .finally(() => setCancelling(false));
  }, [document?.documentId, document?.processingStage, onUploadComplete]);

  const loadVersions = useCallback((docId: string) => {
    setVersionsLoaded(false);
    fetchVersionHistory(docId).then((list) => {
      setVersions(list);
      setVersionsLoaded(true);
    });
  }, []);

  useEffect(() => {
    if (document?.documentId) loadVersions(document.documentId);
  }, [document?.documentId, loadVersions]);

  useEffect(() => {
    if (!document?.documentId) {
      setScreenshots([]);
      setSelectedPage(null);
      return;
    }
    setScreenshotsLoading(true);
    fetchScreenshots(document.documentId)
      .then((list) => {
        setScreenshots(list);
        setSelectedPage((prev) => (list.length > 0 && (prev == null || prev > list.length) ? 1 : prev));
      })
      .catch(() => setScreenshots([]))
      .finally(() => setScreenshotsLoading(false));
  }, [document?.documentId]);

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      const file = acceptedFiles[0];
      if (!file) return;
      setUploading(true);
      simulateUpload(file).then((doc) => {
        setUploading(false);
        onUploadComplete(doc);
      });
    },
    [onUploadComplete]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'], 'application/pdf': ['.pdf'] },
    maxFiles: 1,
    disabled: uploading,
  });

  return (
    <section className="bg-white rounded-lg shadow p-4 sm:p-6 min-w-0">
      <h2 className="text-lg font-semibold text-slate-800 mb-4">1. Document Intake Panel</h2>

      {/* Upload */}
      <div className="mb-4 sm:mb-6">
        <div
          {...getRootProps()}
          className={`border-2 border-dashed rounded-lg p-6 sm:p-8 text-center cursor-pointer transition-colors ${
            isDragActive ? 'border-slate-500 bg-slate-100' : 'border-slate-300 hover:border-slate-400'
          } ${uploading ? 'opacity-60 pointer-events-none' : ''}`}
        >
          <input {...getInputProps()} />
          {uploading ? (
            <p className="text-slate-600">Uploading…</p>
          ) : (
            <p className="text-slate-600">{isDragActive ? 'Drop file here' : 'Drag & drop .docx or .pdf here, or click to select'}</p>
          )}
        </div>
      </div>

      {/* In-progress loading banner */}
      {document && isInProgress(document.processingStage) && (
        <div className="mb-4 flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
          <div className="h-8 w-8 flex-shrink-0">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-amber-400 border-t-transparent" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-medium text-amber-800">Processing in progress</div>
            <div className="text-sm text-amber-700">Extracting and comparing — this page will refresh when done.</div>
          </div>
          <button
            type="button"
            onClick={handleCancelJob}
            disabled={cancelling}
            className="shrink-0 px-3 py-1.5 rounded bg-red-600 text-white text-sm font-medium hover:bg-red-700 disabled:opacity-50"
          >
            {cancelling ? 'Cancelling…' : 'Cancel'}
          </button>
        </div>
      )}

      {/* Status (when a document is selected) */}
      {document && (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 sm:gap-4 mb-4 sm:mb-6">
          <div className="border border-slate-200 rounded p-3">
            <div className="text-xs text-slate-500 uppercase mb-1">Upload status</div>
            <div className="font-medium capitalize">{document.uploadStatus}</div>
          </div>
          <div className="border border-slate-200 rounded p-3">
            <div className="text-xs text-slate-500 uppercase mb-1">Processing stage</div>
            <div className="flex items-center gap-2">
              <span className="font-medium">{STAGE_LABELS[document.processingStage]}</span>
              {isInProgress(document.processingStage) && (
                <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-400 border-t-transparent" />
              )}
              {document.processingStage === 'cancelled' && (
                <span className="text-slate-500 text-sm">(job stopped)</span>
              )}
            </div>
          </div>
          <div className="border border-slate-200 rounded p-3">
            <div className="text-xs text-slate-500 uppercase mb-1">Validation status</div>
            <span
              className={`inline-block px-2 py-0.5 rounded text-sm font-medium ${
                document.validationStatus === 'structurally_verified' || document.validationStatus === 'training_approved'
                  ? 'bg-green-100 text-green-800'
                  : document.validationStatus === 'integrity_conflict'
                  ? 'bg-amber-100 text-amber-800'
                  : document.validationStatus === 'screenshot_failed' || document.validationStatus === 'validation_failed'
                  ? 'bg-red-100 text-red-800'
                  : 'bg-slate-100 text-slate-700'
              }`}
            >
              {VALIDATION_LABELS[document.validationStatus] ?? document.validationStatus}
            </span>
          </div>
          {document.fileSizeBytes != null && (
            <div className="border border-slate-200 rounded p-3">
              <div className="text-xs text-slate-500 uppercase mb-1">File size</div>
              <div className="font-medium">{(document.fileSizeBytes / 1024).toFixed(1)} KB</div>
            </div>
          )}
          {document.pageCount != null && (
            <div className="border border-slate-200 rounded p-3">
              <div className="text-xs text-slate-500 uppercase mb-1">Pages</div>
              <div className="font-medium">{document.pageCount}</div>
            </div>
          )}
        </div>
      )}
      {document?.processingStage === 'error' && (document.errorType || document.errorMessage) && (
        <div className="mb-4 p-3 rounded bg-red-50 border border-red-200">
          <div className="text-xs text-red-600 uppercase mb-1">Failure</div>
          {document.errorType && <div className="font-medium text-red-800">{document.errorType}</div>}
          {document.errorMessage && <div className="text-sm text-red-700 mt-1">{document.errorMessage}</div>}
        </div>
      )}

      {/* Page Screenshots — pagination like Structural Comparison Viewer */}
      {document?.documentId && (
        <div className="mb-4 sm:mb-6">
          <h3 className="text-sm font-medium text-slate-700 mb-2">Page Screenshots</h3>
          {screenshotsLoading ? (
            <p className="text-slate-500 text-sm">Loading screenshots…</p>
          ) : screenshots.length === 0 ? (
            <p className="text-slate-500 text-sm">No screenshots (PDF only, generated after upload).</p>
          ) : (
            <>
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <span className="text-sm text-slate-600">Select page:</span>
                <select
                  value={selectedPage ?? ''}
                  onChange={(e) => setSelectedPage(e.target.value ? Number(e.target.value) : null)}
                  className="rounded border border-slate-300 px-2 py-1 text-sm bg-white"
                >
                  <option value="">—</option>
                  {screenshots.map((s) => (
                    <option key={s.pageNumber} value={s.pageNumber}>{s.pageNumber}</option>
                  ))}
                </select>
                <span className="text-slate-500 text-sm">of {screenshots.length}</span>
              </div>
              {selectedPage != null && (
                <div className="mb-4 border border-slate-200 rounded overflow-hidden bg-slate-50">
                  <div className="p-3">
                    <div className="text-xs font-semibold text-slate-500 uppercase mb-2">Page {selectedPage}</div>
                    <button
                      type="button"
                      onClick={() => setModalPage(selectedPage)}
                      className="block w-full max-w-md rounded border border-slate-200 overflow-hidden bg-white hover:border-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-400"
                    >
                      <img
                        src={screenshotUrl(document.documentId, selectedPage)}
                        alt={`Page ${selectedPage}`}
                        className="w-full h-auto max-h-[420px] object-contain object-top"
                      />
                    </button>
                    <p className="mt-1 text-xs text-slate-500">Click image to open full size</p>
                  </div>
                </div>
              )}
              <div className="flex gap-2 overflow-x-auto pb-2 min-h-0">
                <span className="text-sm text-slate-600 shrink-0 self-center">Go to page:</span>
                {screenshots.map((s) => (
                  <button
                    key={s.pageNumber}
                    type="button"
                    onClick={() => setSelectedPage(s.pageNumber)}
                    onMouseEnter={() => setHoverPage(s.pageNumber)}
                    onMouseLeave={() => setHoverPage(null)}
                    className={`shrink-0 w-12 rounded border overflow-hidden bg-slate-100 focus:outline-none focus:ring-2 focus:ring-slate-400 ${
                      selectedPage === s.pageNumber ? 'border-amber-500 ring-2 ring-amber-200 bg-amber-50' : 'border-slate-200 hover:border-slate-400'
                    }`}
                  >
                    <img
                      src={screenshotUrl(document.documentId, s.pageNumber)}
                      alt={`Page ${s.pageNumber}`}
                      className="w-full aspect-[3/4] object-cover object-top"
                    />
                    <span className={`block text-xs text-center py-0.5 ${selectedPage === s.pageNumber ? 'text-amber-800 font-medium' : 'text-slate-600'}`}>
                      {s.pageNumber}
                    </span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {modalPage != null && document?.documentId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
          aria-label="Screenshot full size"
          onClick={() => setModalPage(null)}
        >
          <div className="relative max-w-[90vw] max-h-[90vh] bg-white rounded-lg shadow-xl overflow-hidden" onClick={(e) => e.stopPropagation()}>
            <img
              src={screenshotUrl(document.documentId, modalPage)}
              alt={`Page ${modalPage} full size`}
              className="max-w-full max-h-[90vh] object-contain"
            />
            <button
              type="button"
              onClick={() => setModalPage(null)}
              className="absolute top-2 right-2 rounded bg-slate-800 text-white px-3 py-1 text-sm hover:bg-slate-700"
            >
              Close
            </button>
          </div>
        </div>
      )}

      {/* Version history */}
      <div>
        <h3 className="text-sm font-medium text-slate-700 mb-2">Version history</h3>
        {!document ? (
          <p className="text-slate-500 text-sm">Select or upload a document to see version history.</p>
        ) : !versionsLoaded ? (
          <p className="text-slate-500 text-sm">Loading…</p>
        ) : versions.length === 0 ? (
          <p className="text-slate-500 text-sm">No versions yet.</p>
        ) : (
          <ul className="border border-slate-200 rounded divide-y overflow-hidden">
            {versions.map((v) => (
              <li key={`${v.documentId}-${v.version}`} className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-1 px-3 py-2 text-sm min-w-0">
                <span className="font-medium truncate">{v.name}</span>
                <span className="text-slate-500 text-xs sm:text-sm shrink-0">v{v.version} · {new Date(v.createdAt).toLocaleString()}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
