# Knowledge Ingestion Admin Console (Phase 1)

React dashboard for the **Verifiable Knowledge Ingestion System** — Document Intake, Structural Comparison, Chapter Explorer, Validation Console, and Audit Logs. All data is mocked; ready for backend integration in Phase 2.

## Run the app

```bash
cd frontend
npm install
npm run dev
```

Then open [http://new.packt.localhost:8003](http://new.packt.localhost:8003).

If `npm install` fails with permission errors (e.g. `EACCES` on `.npm`), either fix cache ownership once:

```bash
sudo chown -R $(whoami) ~/.npm
```

or use a local cache in the project:

```bash
npm install --cache ./.npm-cache
```

## Build

```bash
npm run build
npm run preview   # optional: serve production build
```

## Mock data and API contracts

- **Location:** `src/api/mock.ts` — in-memory data and async helpers that simulate network delay.
- **Types:** `src/types/` — `document.ts`, `structure.ts`, `comparison.ts`, `validation.ts`, `audit.ts`.

Backend can replace the mock by implementing the same shapes and swapping the imports in `Dashboard.tsx` and each panel component to call real APIs instead of `fetchDocuments`, `fetchStructure`, `fetchComparison`, `fetchValidationItems`, `fetchAuditLogs`, `fetchVersionHistory`, and `simulateUpload` / `updateValidationStatus`.

### Data contracts (for Phase 2)

| Area | Key types / fields |
|------|---------------------|
| Document | `DocumentSummary`: documentId, name, uploadStatus, processingStage, validationStatus, version, hash, createdAt |
| Structure | `DocumentStructure`: documentId, source (docx/pdf), chapters[] with chapter_id, heading, content_blocks[], order_index |
| Comparison | `ComparisonResult`: chapterCountMatch, headingMatch, paragraphCountMatch, tableCountMatch, pageCountMatch, wordCountMatch, mismatches[] |
| Validation | `ValidationItem`: id, documentId, documentName, confidence, conflictReason, status, comments[] |
| Audit | `AuditLogEntry`: timestamp, parserVersion, validationResult, reviewer, action |

## Features (Phase 1)

1. **Document Intake Panel** — Drag-and-drop upload (.docx/.pdf), upload/processing/validation status, version history list.
2. **Structural Comparison Viewer** — Side-by-side DOCX vs PDF structure, mismatch highlighting, optional per-chapter diff.
3. **Chapter Explorer** — Expandable chapter → section → block tree, word counts, inline diff when a node is selected.
4. **Validation Console** — Conflict queue, confidence bar, Approve/Reject, comment log per item.
5. **Audit Logs** — Table (timestamp, parser version, validation result, reviewer, action), filter by document, sort by time.

Document selector at the top drives which document’s data is shown across panels. Multiple mock documents are provided; upload adds another (in memory only).
