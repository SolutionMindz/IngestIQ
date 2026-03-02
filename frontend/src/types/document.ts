export type UploadStatus = 'idle' | 'uploading' | 'uploaded' | 'failed';
export type ProcessingStage = 'pending' | 'extracting' | 'comparing' | 'done' | 'error' | 'cancelled';
export type ValidationStatus = 'pending' | 'structurally_verified' | 'integrity_conflict' | 'training_approved' | 'screenshot_failed' | 'validation_failed';

export interface DocumentSummary {
  documentId: string;
  name: string;
  uploadStatus: UploadStatus;
  processingStage: ProcessingStage;
  validationStatus: ValidationStatus;
  version: string;
  hash: string;
  createdAt: string;
  author?: string;
  fileSizeBytes?: number;
  pageCount?: number;
  errorType?: string;
  errorMessage?: string;
}

export interface DocumentVersion {
  documentId: string;
  version: string;
  name: string;
  createdAt: string;
}
