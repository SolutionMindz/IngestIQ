export type A2ITaskStatus =
  | 'pending'
  | 'assigned'
  | 'in_review'
  | 'under_review'
  | 'completed'
  | 'auto_verified'
  | 'failed';

export type DiffAction = 'accepted_textract' | 'accepted_native' | 'edited' | 'rejected' | null;

export interface DiffItem {
  id: string;
  diffType: 'changed_word' | 'missing_word' | 'extra_word' | 'table_mismatch';
  nativeValue: string;
  textractValue: string;
  lineIndex: number;
  action?: DiffAction;
  correctedValue?: string;
}

export interface A2ITask {
  id: string;
  documentId: string;
  pageNumber: number;
  humanLoopName?: string;
  status: A2ITaskStatus;
  triggerReason: string;
  reviewerId?: string;
  reviewTimestamp?: string;
  correctionApplied: boolean;
  confidenceScore?: number;
  s3OutputUri?: string;
  assignedTo?: string;
  assignedAt?: string;
  createdAt: string;
}

export interface A2ITaskDetail extends A2ITask {
  diffItems: DiffItem[];
  nativeTextSnapshot?: string;
  originalTextractText?: string;
}

export interface ReviewerStats {
  reviewerId: string;
  totalAssigned: number;
  completed: number;
  pending: number;
  correctionsApplied: number;
  acceptanceRate: number;
}
