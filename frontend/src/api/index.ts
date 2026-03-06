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

export const fetchA2ITasks = useBackend ? client.fetchA2ITasks : mock.fetchA2ITasks;
export const fetchA2ITask = useBackend ? client.fetchA2ITask : mock.fetchA2ITask;
export const triggerA2IReview = useBackend ? client.triggerA2IReview : mock.triggerA2IReview;
export const submitA2ICorrection = useBackend ? client.submitA2ICorrection : mock.submitA2ICorrection;
export const pollA2IResults = useBackend ? client.pollA2IResults : mock.pollA2IResults;
export const fetchAllA2ITasks = useBackend ? client.fetchAllA2ITasks : mock.fetchAllA2ITasks;
export const fetchA2ITaskDetail = useBackend ? client.fetchA2ITaskDetail : mock.fetchA2ITaskDetail;
export const assignA2ITask = useBackend ? client.assignA2ITask : mock.assignA2ITask;
export const fetchReviewerStats = useBackend ? client.fetchReviewerStats : mock.fetchReviewerStats;

export type { ScreenshotItem, PageAccuracyItem, PageValidationEntry, PageComparisonSummary, PageMarkdownResponse } from './client';
