export interface AuditLogEntry {
  id: string;
  documentId: string;
  documentName?: string;
  timestamp: string;
  parserVersion: string;
  validationResult: string;
  reviewer: string;
  action: string;
}
