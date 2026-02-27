import * as mock from './mock';
import * as client from './client';

const useBackend = import.meta.env.VITE_USE_API === 'true';

export const fetchDocuments = useBackend ? client.fetchDocuments : mock.fetchDocuments;
export const fetchDocumentById = useBackend ? client.fetchDocumentById : mock.fetchDocumentById;
export const fetchVersionHistory = useBackend ? client.fetchVersionHistory : mock.fetchVersionHistory;
export const fetchStructure = useBackend ? client.fetchStructure : mock.fetchStructure;
export const fetchComparison = useBackend ? client.fetchComparison : mock.fetchComparison;
export const fetchValidationItems = useBackend ? client.fetchValidationItems : mock.fetchValidationItems;
export const fetchAuditLogs = useBackend ? client.fetchAuditLogs : mock.fetchAuditLogs;
export const simulateUpload = useBackend ? client.uploadDocument : mock.simulateUpload;
export const cancelDocumentJob = useBackend ? client.cancelDocumentJob : mock.cancelDocumentJob;
export const updateValidationStatus = useBackend ? client.updateValidationStatus : mock.updateValidationStatus;

export const fetchScreenshots = useBackend ? client.fetchScreenshots : mock.fetchScreenshots;
export const fetchPageAccuracy = useBackend ? client.fetchPageAccuracy : mock.fetchPageAccuracy;
export const fetchPageValidation = useBackend ? client.fetchPageValidation : mock.fetchPageValidation;
export const fetchPageComparisonSummary = useBackend ? client.fetchPageComparisonSummary : mock.fetchPageComparisonSummary;
export const fetchPageMarkdown = useBackend ? client.fetchPageMarkdown : mock.fetchPageMarkdown;
export const postPageValidation = useBackend ? client.postPageValidation : mock.postPageValidation;
export const screenshotUrl = useBackend ? client.screenshotUrl : mock.screenshotUrl;

export type { ScreenshotItem, PageAccuracyItem, PageValidationEntry, PageComparisonSummary, PageMarkdownResponse } from './client';
