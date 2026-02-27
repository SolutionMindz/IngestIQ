export type ContentBlockType = 'text' | 'code' | 'table' | 'image';

export interface BoundingBox {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface ContentBlock {
  id: string;
  type: ContentBlockType;
  content: string;
  orderIndex: number;
  wordCount?: number;
  bbox?: BoundingBox;
}

export interface Section {
  id: string;
  heading: string;
  level: number; // 2 = Heading 2, 3 = Heading 3
  contentBlocks: ContentBlock[];
  orderIndex: number;
  wordCount?: number;
}

export interface Chapter {
  chapter_id: string;
  heading: string;
  content_blocks: ContentBlock[];
  sections?: Section[];
  order_index: number;
  wordCount?: number;
}

export interface DocumentStructure {
  documentId: string;
  source: 'docx' | 'pdf' | 'textract';
  chapters: Chapter[];
  totalWordCount?: number;
  pageCount?: number;
}
