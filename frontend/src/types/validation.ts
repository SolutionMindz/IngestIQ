export type ValidationItemStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'pending_review'
  | 'under_review'
  | 'human_verified'
  | 'auto_verified';

export interface ValidationComment {
  id: string;
  author: string;
  text: string;
  createdAt: string;
}

export interface ValidationItem {
  id: string;
  documentId: string;
  documentName: string;
  confidence: number; // 0-100
  conflictReason: string;
  reviewer?: string;
  status: ValidationItemStatus;
  comments: ValidationComment[];
  createdAt: string;
}
