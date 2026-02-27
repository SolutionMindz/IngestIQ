export interface Mismatch {
  id: string;
  type: 'chapter' | 'heading' | 'paragraph' | 'table' | 'page' | 'word_count';
  docxRef?: string;
  pdfRef?: string;
  message: string;
  chapterIndex?: number;
  blockId?: string;
}

export interface ComparisonResult {
  documentId: string;
  chapterCountMatch: boolean;
  headingMatch: boolean;
  paragraphCountMatch: boolean;
  tableCountMatch: boolean;
  pageCountMatch: boolean;
  wordCountMatch: boolean;
  mismatches: Mismatch[];
  docxChapterCount: number;
  pdfChapterCount: number;
  docxWordCount: number;
  pdfWordCount: number;
}
