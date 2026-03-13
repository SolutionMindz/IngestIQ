import { useState, useEffect, useRef } from 'react';
import type { DocumentSummary } from '../types/document';
import { fetchDocuments, fetchDocumentById } from '../api';
import DocumentIntake from '../components/DocumentIntake/DocumentIntake';
import StructuralComparison from '../components/StructuralComparison/StructuralComparison';
import ChapterExplorer from '../components/ChapterExplorer/ChapterExplorer';
import ValidationConsole from '../components/ValidationConsole/ValidationConsole';
import AuditLogs from '../components/AuditLogs/AuditLogs';

const IN_PROGRESS_STAGES: DocumentSummary['processingStage'][] = ['pending', 'extracting', 'comparing'];

export default function Dashboard() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    fetchDocuments()
      .then((list) => {
        if (!cancelled) {
          setDocuments(list);
          setSelectedDocumentId((prev) => (list.length > 0 && !prev ? list[0].documentId : prev));
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setDocuments([]);
          setLoadError(err instanceof Error ? err.message : 'Failed to load documents');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, []);

  const selectedDoc = documents.find((d) => d.documentId === selectedDocumentId) ?? null;
  const isProcessing = selectedDoc && IN_PROGRESS_STAGES.includes(selectedDoc.processingStage);

  // Poll when selected document is in progress; refresh on done/error
  useEffect(() => {
    if (!selectedDocumentId || !isProcessing) {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }
    let failures = 0;
    const poll = () => {
      fetchDocumentById(selectedDocumentId)
        .then((doc) => {
          failures = 0;
          if (!doc) return;
          setDocuments((prev) => prev.map((d) => (d.documentId === selectedDocumentId ? doc : d)));
          if (doc.processingStage === 'done' || doc.processingStage === 'error' || doc.processingStage === 'cancelled') {
            if (pollRef.current) {
              clearInterval(pollRef.current);
              pollRef.current = null;
            }
          }
        })
        .catch(() => {
          failures += 1;
          if (failures >= 3 && pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
        });
    };
    poll();
    pollRef.current = setInterval(poll, 2000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
    };
  }, [selectedDocumentId, isProcessing]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-slate-800" />
      </div>
    );
  }

  return (
    <div className="space-y-4 sm:space-y-6 min-w-0">
      {/* Document selector */}
      <div className="bg-white rounded-lg shadow p-4 sm:p-4">
        {loadError && (
          <div className="mb-4 p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-sm">
            {loadError}. Ensure the backend is running (e.g. <code className="bg-amber-100 px-1 rounded">{import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8889'}</code>).
          </div>
        )}
        <label className="block text-sm font-medium text-slate-700 mb-2">Select document</label>
        <select
          className="w-full max-w-full sm:max-w-md border border-slate-300 rounded px-3 py-2 bg-white"
          value={selectedDocumentId ?? ''}
          onChange={(e) => setSelectedDocumentId(e.target.value || null)}
        >
          <option value="">— Select —</option>
          {documents.map((d) => (
            <option key={d.documentId} value={d.documentId}>
              {d.name}
            </option>
          ))}
        </select>
      </div>

      {/* 1. Document Intake Panel */}
      <DocumentIntake
        document={selectedDoc}
        onUploadComplete={(doc) => {
          setDocuments((prev) => [...prev, doc]);
          setSelectedDocumentId(doc.documentId);
        }}
      />

      {/* 2. Structural Comparison Viewer — key so it refetches when doc finishes processing */}
      <StructuralComparison key={`struct-${selectedDocumentId}-${selectedDoc?.processingStage ?? ''}`} documentId={selectedDocumentId} />

      {/* 3. Chapter Explorer */}
      <ChapterExplorer key={`ch-${selectedDocumentId}-${selectedDoc?.processingStage ?? ''}`} documentId={selectedDocumentId} />

      {/* 4. Validation Console */}
      <ValidationConsole key={`val-${selectedDocumentId}-${selectedDoc?.processingStage ?? ''}`} documentId={selectedDocumentId} documentValidationStatus={selectedDoc?.validationStatus} />

      {/* 5. Audit Logs */}
      <AuditLogs key={`audit-${selectedDocumentId}-${selectedDoc?.processingStage ?? ''}`} documentId={selectedDocumentId} />
    </div>
  );
}
