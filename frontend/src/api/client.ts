import type { DocumentSummary, DocumentVersion } from '../types/document';
import type { DocumentStructure } from '../types/structure';
import type { ComparisonResult } from '../types/comparison';
import type { ValidationItem } from '../types/validation';
import type { AuditLogEntry } from '../types/audit';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8889';

const REQUEST_TIMEOUT_MS = 15000;

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...options?.headers },
    });
    clearTimeout(timeoutId);
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`${res.status}: ${text}`);
    }
    if (res.status === 204) return undefined as T;
    return res.json();
  } catch (err) {
    clearTimeout(timeoutId);
    if (err instanceof Error) {
      if (err.name === 'AbortError') {
        throw new Error(`Request timed out. Is the backend running at ${API_BASE}?`);
      }
      throw err;
    }
    throw err;
  }
}

export async function fetchDocuments(): Promise<DocumentSummary[]> {
  return request<DocumentSummary[]>('/api/documents');
}

export async function fetchDocumentById(documentId: string): Promise<DocumentSummary | null> {
  const doc = await request<DocumentSummary | null>(`/api/documents/${documentId}`);
  return doc ?? null;
}

export async function fetchVersionHistory(documentId: string): Promise<DocumentVersion[]> {
  return request<DocumentVersion[]>(`/api/documents/${documentId}/versions`);
}

export async function fetchStructure(documentId: string, source: 'docx' | 'pdf' | 'textract'): Promise<DocumentStructure | null> {
  const s = await request<DocumentStructure | null>(`/api/documents/${documentId}/structure?source=${source}`);
  return s ?? null;
}

export async function fetchComparison(documentId: string): Promise<ComparisonResult | null> {
  const c = await request<ComparisonResult | null>(`/api/documents/${documentId}/comparison`);
  return c ?? null;
}

export async function fetchValidationItems(documentId?: string): Promise<ValidationItem[]> {
  const q = documentId ? `?documentId=${encodeURIComponent(documentId)}` : '';
  return request<ValidationItem[]>(`/api/validation${q}`);
}

export async function fetchAuditLogs(documentId?: string): Promise<AuditLogEntry[]> {
  const q = documentId ? `?documentId=${encodeURIComponent(documentId)}` : '';
  return request<AuditLogEntry[]>(`/api/audit${q}`);
}

export async function uploadDocument(file: File): Promise<DocumentSummary> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_BASE}/api/documents/upload`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

export async function cancelDocumentJob(documentId: string): Promise<DocumentSummary> {
  return request<DocumentSummary>(`/api/documents/${documentId}/cancel`, { method: 'POST' });
}

export async function updateValidationStatus(
  itemId: string,
  status: ValidationItem['status'],
  reviewer?: string,
  comment?: string
): Promise<ValidationItem> {
  const endpoint = status === 'approved' ? 'approve' : 'reject';
  const body = JSON.stringify({ reviewer, comment });
  return request<ValidationItem>(`/api/validation/${itemId}/${endpoint}`, {
    method: 'POST',
    body: body || undefined,
    headers: { 'Content-Type': 'application/json' },
  });
}

// --- Page screenshots & validation ---
export interface ScreenshotItem {
  pageNumber: number;
  path: string;
  checksum: string | null;
}

export function screenshotUrl(documentId: string, pageNumber: number): string {
  return `${API_BASE}/api/documents/${documentId}/screenshots/${pageNumber}`;
}

export async function fetchScreenshots(documentId: string): Promise<ScreenshotItem[]> {
  return request<ScreenshotItem[]>(`/api/documents/${documentId}/screenshots`);
}

export interface PageAccuracyItem {
  pageNumber: number;
  accuracyPct: number;
  wordMatchPct: number | null;
  charMatchPct: number | null;
  structuralMatchPct: number | null;
  status: 'OK' | 'WARNING' | 'ERROR';
}

export async function fetchPageAccuracy(documentId: string): Promise<PageAccuracyItem[]> {
  return request<PageAccuracyItem[]>(`/api/documents/${documentId}/page-accuracy`);
}

export interface PageValidationEntry {
  reviewer: string;
  status: string;
  comment: string | null;
  timestamp: string | null;
}

export async function fetchPageValidation(documentId: string, pageNumber: number): Promise<PageValidationEntry | null> {
  const v = await request<PageValidationEntry | null>(`/api/documents/${documentId}/pages/${pageNumber}/validation`);
  return v ?? null;
}

export interface PageComparisonSummary {
  pageNumber: number;
  wordCountNative: number;
  wordCountTextract: number;
  blockCountNative: number;
  blockCountTextract: number;
  tableCountNative: number;
  tableCountTextract: number;
  missingBlockCount: number;
  accuracyScore: number | null;
  validationStatus: string | null;
  confidenceAvgTextract: number | null;
}

export async function fetchPageComparisonSummary(
  documentId: string,
  pageNumber: number
): Promise<PageComparisonSummary | null> {
  const s = await request<PageComparisonSummary | null>(
    `/api/documents/${documentId}/pages/${pageNumber}/comparison-summary`
  );
  return s ?? null;
}

export interface PageMarkdownResponse {
  markdown: string;
  pageNumber: number;
}

export async function fetchPageMarkdown(
  documentId: string,
  pageNumber: number,
  source?: 'pdf' | 'textract'
): Promise<PageMarkdownResponse | null> {
  try {
    const qs = source ? `?source=${encodeURIComponent(source)}` : '';
    const r = await request<PageMarkdownResponse>(
      `/api/documents/${documentId}/pages/${pageNumber}/markdown${qs}`
    );
    return r ?? null;
  } catch {
    return null;
  }
}

export async function postPageValidation(
  documentId: string,
  pageNumber: number,
  body: { reviewer?: string; status?: string; comment?: string }
): Promise<void> {
  await request(`/api/documents/${documentId}/pages/${pageNumber}/validation`, {
    method: 'POST',
    body: JSON.stringify(body),
    headers: { 'Content-Type': 'application/json' },
  });
}
