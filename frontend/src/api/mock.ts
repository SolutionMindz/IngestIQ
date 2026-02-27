import type { DocumentSummary, DocumentVersion } from '../types/document';
import type { DocumentStructure } from '../types/structure';
import type { ComparisonResult } from '../types/comparison';
import type { ValidationItem } from '../types/validation';
import type { AuditLogEntry } from '../types/audit';

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

const MOCK_DOCUMENTS: DocumentSummary[] = [
  {
    documentId: 'doc-1',
    name: 'Technical Book Sample.docx',
    uploadStatus: 'uploaded',
    processingStage: 'done',
    validationStatus: 'structurally_verified',
    version: '1.0',
    hash: 'a1b2c3d4e5f6',
    createdAt: '2025-02-20T10:00:00Z',
    author: 'Jane Doe',
  },
  {
    documentId: 'doc-2',
    name: 'API Design Guide.pdf',
    uploadStatus: 'uploaded',
    processingStage: 'done',
    validationStatus: 'integrity_conflict',
    version: '2.1',
    hash: 'f6e5d4c3b2a1',
    createdAt: '2025-02-22T14:30:00Z',
    author: 'John Smith',
  },
];

const MOCK_VERSIONS: DocumentVersion[] = [
  { documentId: 'doc-1', version: '1.0', name: 'Technical Book Sample.docx', createdAt: '2025-02-20T10:00:00Z' },
  { documentId: 'doc-1', version: '0.9', name: 'Technical Book Sample.docx', createdAt: '2025-02-18T09:00:00Z' },
  { documentId: 'doc-2', version: '2.1', name: 'API Design Guide.pdf', createdAt: '2025-02-22T14:30:00Z' },
  { documentId: 'doc-2', version: '2.0', name: 'API Design Guide.pdf', createdAt: '2025-02-15T11:00:00Z' },
];

const createMockStructure = (documentId: string, source: 'docx' | 'pdf' | 'textract', hasMismatch = false): DocumentStructure => ({
  documentId,
  source,
  totalWordCount: source === 'docx' ? 12500 : hasMismatch ? 12480 : 12500,
  pageCount: 45,
  chapters: [
    {
      chapter_id: 'ch-1',
      heading: 'Chapter 1: Introduction',
      order_index: 0,
      wordCount: 1200,
      content_blocks: [
        { id: 'b1', type: 'text', content: 'This chapter introduces the main concepts.', orderIndex: 0, wordCount: 8 },
        { id: 'b2', type: 'text', content: 'We will cover fundamentals first.', orderIndex: 1, wordCount: 6 },
      ],
      sections: [
        {
          id: 'sec-1-1',
          heading: 'Overview',
          level: 2,
          orderIndex: 0,
          wordCount: 400,
          contentBlocks: [
            { id: 'b3', type: 'text', content: 'Overview content here.', orderIndex: 0, wordCount: 3 },
          ],
        },
      ],
    },
    {
      chapter_id: 'ch-2',
      heading: 'Chapter 2: Core Concepts',
      order_index: 1,
      wordCount: 3500,
      content_blocks: [
        { id: 'b4', type: 'text', content: 'Core concepts are essential.', orderIndex: 0, wordCount: 4 },
        {
          id: 'b5',
          type: 'code',
          content: 'function example() {\n  return true;\n}',
          orderIndex: 1,
          wordCount: 6,
        },
      ],
      sections: [
        {
          id: 'sec-2-1',
          heading: 'Data Structures',
          level: 2,
          orderIndex: 0,
          wordCount: 800,
          contentBlocks: [
            { id: 'b6', type: 'text', content: 'Data structures section text.', orderIndex: 0, wordCount: 4 },
          ],
        },
      ],
    },
    {
      chapter_id: 'ch-3',
      heading: hasMismatch && source === 'pdf' ? 'Chapter 3: Advanced Topix' : 'Chapter 3: Advanced Topics',
      order_index: 2,
      wordCount: 2800,
      content_blocks: [
        { id: 'b7', type: 'text', content: 'Advanced topics follow.', orderIndex: 0, wordCount: 3 },
      ],
      sections: [],
    },
  ],
});

const MOCK_COMPARISON: Record<string, ComparisonResult> = {
  'doc-1': {
    documentId: 'doc-1',
    chapterCountMatch: true,
    headingMatch: true,
    paragraphCountMatch: true,
    tableCountMatch: true,
    pageCountMatch: true,
    wordCountMatch: true,
    docxChapterCount: 3,
    pdfChapterCount: 3,
    docxWordCount: 12500,
    pdfWordCount: 12500,
    mismatches: [],
  },
  'doc-2': {
    documentId: 'doc-2',
    chapterCountMatch: true,
    headingMatch: false,
    paragraphCountMatch: true,
    tableCountMatch: true,
    pageCountMatch: true,
    wordCountMatch: false,
    docxChapterCount: 3,
    pdfChapterCount: 3,
    docxWordCount: 12500,
    pdfWordCount: 12480,
    mismatches: [
      { id: 'm1', type: 'heading', message: 'Heading text differs', chapterIndex: 2, docxRef: 'Chapter 3: Advanced Topics', pdfRef: 'Chapter 3: Advanced Topix' },
      { id: 'm2', type: 'word_count', message: 'Word count differs by 20', docxRef: '12500', pdfRef: '12480' },
    ],
  },
};

const MOCK_VALIDATION_ITEMS: ValidationItem[] = [
  {
    id: 'val-1',
    documentId: 'doc-2',
    documentName: 'API Design Guide.pdf',
    confidence: 94,
    conflictReason: 'Heading mismatch in Chapter 3; word count variance.',
    status: 'pending',
    comments: [
      { id: 'c1', author: 'System', text: 'Auto-flagged due to confidence < 98%', createdAt: '2025-02-22T14:35:00Z' },
    ],
    createdAt: '2025-02-22T14:35:00Z',
  },
  {
    id: 'val-2',
    documentId: 'doc-1',
    documentName: 'Technical Book Sample.docx',
    confidence: 99,
    conflictReason: 'None',
    status: 'approved',
    reviewer: 'Alice',
    comments: [],
    createdAt: '2025-02-20T11:00:00Z',
  },
];

const MOCK_AUDIT: AuditLogEntry[] = [
  { id: 'a1', documentId: 'doc-1', documentName: 'Technical Book Sample.docx', timestamp: '2025-02-20T11:00:00Z', parserVersion: '1.2.0', validationResult: 'Structurally Verified', reviewer: 'Alice', action: 'Approved' },
  { id: 'a2', documentId: 'doc-1', documentName: 'Technical Book Sample.docx', timestamp: '2025-02-20T10:05:00Z', parserVersion: '1.2.0', validationResult: 'Match', reviewer: 'System', action: 'Extraction completed' },
  { id: 'a3', documentId: 'doc-2', documentName: 'API Design Guide.pdf', timestamp: '2025-02-22T14:35:00Z', parserVersion: '1.2.0', validationResult: 'Integrity Conflict', reviewer: 'System', action: 'Flagged for review' },
];

export async function fetchDocuments(): Promise<DocumentSummary[]> {
  await delay(400);
  return [...MOCK_DOCUMENTS];
}

export async function fetchDocumentById(documentId: string): Promise<DocumentSummary | null> {
  await delay(200);
  return MOCK_DOCUMENTS.find((d) => d.documentId === documentId) ?? null;
}

export async function fetchVersionHistory(documentId: string): Promise<DocumentVersion[]> {
  await delay(300);
  return MOCK_VERSIONS.filter((v) => v.documentId === documentId).sort(
    (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
  );
}

export async function fetchStructure(documentId: string, source: 'docx' | 'pdf' | 'textract'): Promise<DocumentStructure | null> {
  await delay(350);
  const hasMismatch = documentId === 'doc-2' && (source === 'pdf' || source === 'textract');
  return createMockStructure(documentId, source, hasMismatch);
}

export async function fetchComparison(documentId: string): Promise<ComparisonResult | null> {
  await delay(300);
  return MOCK_COMPARISON[documentId] ?? null;
}

export async function fetchValidationItems(documentId?: string): Promise<ValidationItem[]> {
  await delay(350);
  if (documentId) return MOCK_VALIDATION_ITEMS.filter((v) => v.documentId === documentId);
  return [...MOCK_VALIDATION_ITEMS];
}

export async function fetchAuditLogs(documentId?: string): Promise<AuditLogEntry[]> {
  await delay(300);
  let list = [...MOCK_AUDIT].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  if (documentId) list = list.filter((e) => e.documentId === documentId);
  return list;
}

// Simulated upload: add a "new" document to local state (in real app this would be server)
export async function simulateUpload(file: File): Promise<DocumentSummary> {
  await delay(1500);
  const doc: DocumentSummary = {
    documentId: `doc-${Date.now()}`,
    name: file.name,
    uploadStatus: 'uploaded',
    processingStage: 'pending',
    validationStatus: 'pending',
    version: '1.0',
    hash: 'pending',
    createdAt: new Date().toISOString(),
  };
  MOCK_DOCUMENTS.push(doc);
  return doc;
}

// Update validation item status (local state only)
export function updateValidationStatus(
  itemId: string,
  status: ValidationItem['status'],
  reviewer?: string,
  comment?: string
): void {
  const item = MOCK_VALIDATION_ITEMS.find((v) => v.id === itemId);
  if (item) {
    item.status = status;
    if (reviewer) item.reviewer = reviewer;
    if (comment)
      item.comments.push({
        id: `c-${Date.now()}`,
        author: reviewer ?? 'User',
        text: comment,
        createdAt: new Date().toISOString(),
      });
  }
}

// Page screenshots & validation (mock: no data)
export async function fetchScreenshots(_documentId: string): Promise<{ pageNumber: number; path: string; checksum: string | null }[]> {
  await delay(100);
  return [];
}

export function screenshotUrl(_documentId: string, _pageNumber: number): string {
  return '#';
}

export async function fetchPageAccuracy(_documentId: string): Promise<{ pageNumber: number; accuracyPct: number; wordMatchPct: number | null; charMatchPct: number | null; structuralMatchPct: number | null; status: 'OK' | 'WARNING' | 'ERROR' }[]> {
  await delay(100);
  return [];
}

export async function fetchPageValidation(_documentId: string, _pageNumber: number): Promise<{ reviewer: string; status: string; comment: string | null; timestamp: string | null } | null> {
  await delay(100);
  return null;
}

export async function postPageValidation(_documentId: string, _pageNumber: number, _body: { reviewer?: string; status?: string; comment?: string }): Promise<void> {
  await delay(100);
}

export async function fetchPageComparisonSummary(
  _documentId: string,
  _pageNumber: number
): Promise<{
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
} | null> {
  await delay(100);
  return null;
}

export async function fetchPageMarkdown(
  _documentId: string,
  pageNumber: number,
  _source?: 'pdf' | 'textract'
): Promise<{ markdown: string; pageNumber: number } | null> {
  await delay(100);
  return { markdown: `# Page ${pageNumber}\n\n(Mock: no markdown content.)`, pageNumber };
}

export async function cancelDocumentJob(documentId: string): Promise<DocumentSummary> {
  await delay(200);
  const doc = MOCK_DOCUMENTS.find((d) => d.documentId === documentId);
  if (doc) {
    doc.processingStage = 'cancelled';
    return { ...doc };
  }
  return {
    documentId,
    name: 'Document',
    uploadStatus: 'uploaded',
    processingStage: 'cancelled',
    validationStatus: 'pending',
    version: '1.0',
    hash: '',
    createdAt: new Date().toISOString(),
  };
}
