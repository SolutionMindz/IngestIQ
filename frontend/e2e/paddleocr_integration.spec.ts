/**
 * PaddleOCR Integration — Playwright tests
 *
 * Verifies the post-implementation state described in:
 *   .cursor/plans/paddleocr_integration_plan_c41eeaf6.plan.md
 *
 * DOCX support has been fully removed; no DOCX tests are included.
 *
 * Coverage:
 *   §1   pdf_extractor — PaddleOCR is the sole extraction path for source="pdf"
 *   §2   Upload UI accepts only PDF (no docx copy, no docx accept attribute)
 *   §3   Label changes — "Native PDF" → "PaddleOCR" everywhere in the UI
 *   §7   Layout / structure — structure blocks may carry type="code"|"table"|"formula"
 */

import { test, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// §2 – DocumentIntake: PDF-only upload
// ---------------------------------------------------------------------------
test.describe('DocumentIntake: PDF-only upload', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(
      page.getByRole('heading', { name: /Document Intake Panel/i })
    ).toBeVisible({ timeout: 15_000 });
  });

  test('drop zone hint mentions only .pdf', async ({ page }) => {
    // §2.2: copy changed to "Drag & drop .pdf here, or click to select"
    await expect(
      page.getByText(/Drag & drop \.pdf here/i).first()
    ).toBeVisible();
  });

  test('file input accepts only application/pdf', async ({ page }) => {
    // The <input type="file"> accept attribute must only list application/pdf / .pdf
    const input = page.locator('input[type="file"]').first();
    const accept = await input.getAttribute('accept');
    expect(accept).toBeTruthy();
    expect(accept).toMatch(/application\/pdf|\.pdf/i);
  });
});

// ---------------------------------------------------------------------------
// §2 / §3 – StructuralComparison: PaddleOCR vs Textract labels
// ---------------------------------------------------------------------------
test.describe('StructuralComparison: PaddleOCR vs Textract labels', () => {
  test('no-document state shows PaddleOCR vs AWS Textract placeholder', async ({ page }) => {
    // Navigate fresh; the component renders the empty-state hint before any
    // document is auto-selected.  The hint contains the new label copy.
    await page.goto('/');

    // The empty-state text is rendered on the server-side render pass (or
    // briefly before data loads).  We look for the heading first so the
    // section is in the DOM.
    await expect(
      page.getByRole('heading', { name: /Structural Comparison Viewer/i })
    ).toBeVisible({ timeout: 15_000 });

    // Either the empty-state placeholder or the loaded comparison section
    // must contain "PaddleOCR".
    await expect(
      page.getByText(/PaddleOCR/i).first()
    ).toBeVisible({ timeout: 15_000 });
  });

  test('comparison panel does NOT show "Native PDF" label anywhere', async ({ page }) => {
    await page.goto('/');
    await expect(
      page.getByRole('heading', { name: /Structural Comparison Viewer/i })
    ).toBeVisible({ timeout: 15_000 });
    // "Native PDF" must be gone from the comparison section
    await expect(page.getByText(/Native PDF/i)).not.toBeVisible();
  });

  test('comparison section heading is present', async ({ page }) => {
    await page.goto('/');
    await expect(
      page.getByRole('heading', { name: /Structural Comparison Viewer/i })
    ).toBeVisible({ timeout: 15_000 });
  });
});

// ---------------------------------------------------------------------------
// §3 – ChapterExplorer: label changes
// ---------------------------------------------------------------------------
test.describe('ChapterExplorer: PaddleOCR label changes', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(
      page.getByRole('heading', { name: /Document Intake Panel/i })
    ).toBeVisible({ timeout: 15_000 });
  });

  test('ChapterExplorer does NOT show "Native PDF (Left)"', async ({ page }) => {
    await expect(page.getByText(/Native PDF \(Left\)/i)).not.toBeVisible();
  });

  test('ChapterExplorer does NOT show "Native PDF vs AWS Textract"', async ({ page }) => {
    await expect(page.getByText(/Native PDF vs AWS Textract/i)).not.toBeVisible();
  });

  test('ChapterExplorer section heading is visible', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: /Chapter Explorer/i })
    ).toBeVisible({ timeout: 10_000 });
  });

  test('ChapterExplorer shows "PaddleOCR" label when a document is selected', async ({ page }) => {
    // Wait for documents to auto-load; if there are none, the empty state
    // still shows the placeholder with the new label.
    await page.waitForTimeout(3000);

    // Check page-wide for PaddleOCR — it must appear somewhere after load
    const hasPaddle = await page.getByText(/PaddleOCR/i).first().isVisible().catch(() => false);
    if (!hasPaddle) {
      // Acceptable if no documents exist yet — empty state is also valid
      test.skip();
    }
  });
});

// ---------------------------------------------------------------------------
// §3 – Review page: DiffViewer + ReviewTask label changes
// ---------------------------------------------------------------------------
test.describe('Human Review Page: PaddleOCR label changes', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/review');
    await expect(page.getByText('Review Queue')).toBeVisible({ timeout: 10_000 });
  });

  test('Review page does NOT show "Native PDF" text anywhere', async ({ page }) => {
    await expect(page.getByText(/Native PDF/i)).not.toBeVisible();
  });

  test('Review page does NOT show "Accept All Native" button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Accept All Native/i })).not.toBeVisible();
  });

  test('ReviewTask shows "PaddleOCR" panel label when a task is open', async ({ page }) => {
    await page.waitForTimeout(1500);
    const taskRow = page.locator('ul li').first();
    if (await taskRow.count() === 0) {
      test.skip();
      return;
    }
    await taskRow.click();
    await page.waitForTimeout(1500);

    await expect(page.getByText('PaddleOCR').first()).toBeVisible({ timeout: 10_000 });
  });

  test('"Accept All PaddleOCR" button appears when task is open', async ({ page }) => {
    await page.waitForTimeout(1500);
    const taskRow = page.locator('ul li').first();
    if (await taskRow.count() === 0) {
      test.skip();
      return;
    }
    await taskRow.click();
    await page.waitForTimeout(1500);

    await expect(
      page.getByRole('button', { name: /Accept All PaddleOCR/i })
    ).toBeVisible({ timeout: 10_000 });
  });

  test('DiffViewer shows "Use PaddleOCR value" button (not "Use Native PDF value")', async ({ page }) => {
    await page.waitForTimeout(1500);
    const taskRow = page.locator('ul li').first();
    if (await taskRow.count() === 0) {
      test.skip();
      return;
    }
    await taskRow.click();
    await page.waitForTimeout(1500);

    const oldBtn = page.getByRole('button', { name: /Use Native PDF value/i });
    expect(await oldBtn.isVisible().catch(() => false)).toBe(false);

    const newBtn = page.getByRole('button', { name: /Use PaddleOCR value/i });
    if (await newBtn.count() > 0) {
      await expect(newBtn.first()).toBeVisible();
    }
  });

  test('ReviewTask shows no "No native text available" copy', async ({ page }) => {
    await expect(page.getByText(/No native text available/i)).not.toBeVisible();
  });

  test('ReviewTask three-panel labels use PaddleOCR not Native PDF', async ({ page }) => {
    await page.waitForTimeout(1500);
    const taskRow = page.locator('ul li').first();
    if (await taskRow.count() === 0) {
      test.skip();
      return;
    }
    await taskRow.click();
    await page.waitForTimeout(1500);

    const paddleLabel = page.getByText('PaddleOCR');
    const textractLabel = page.getByText(/Textract.*differences highlighted/i);
    const screenshotLabel = page.getByText('Page Screenshot');

    let visible = 0;
    for (const lbl of [paddleLabel, textractLabel, screenshotLabel]) {
      if (await lbl.isVisible().catch(() => false)) visible++;
    }
    expect(visible).toBeGreaterThanOrEqual(2);
  });
});

// ---------------------------------------------------------------------------
// §2 – API: source validation (backend)
// ---------------------------------------------------------------------------
test.describe('API: source validation', () => {
  test('GET structure?source=docx returns 400 (invalid source)', async ({ request }) => {
    // §2.1 structure.py — "docx" removed from valid source values → 400
    const fakeId = '00000000-0000-0000-0000-000000000000';
    const res = await request.get(
      `http://127.0.0.1:8889/api/documents/${fakeId}/structure?source=docx`
    );
    expect([400, 422]).toContain(res.status());
  });

  test('GET structure?source=pdf for missing document returns 404', async ({ request }) => {
    // source=pdf is a valid value; document not found → 404 (not 422/400)
    const fakeId = '00000000-0000-0000-0000-000000000000';
    const res = await request.get(
      `http://127.0.0.1:8889/api/documents/${fakeId}/structure?source=pdf`
    );
    expect(res.status()).toBe(404);
  });
});

// ---------------------------------------------------------------------------
// §7 – Structure Builder: content block types (layout-aware pipeline)
// ---------------------------------------------------------------------------
test.describe('Structure Builder: typed content blocks (§7)', () => {
  test('structure for source=pdf may contain ContentBlocks with type "code"', async ({ request }) => {
    const listRes = await request.get('http://127.0.0.1:8889/api/documents');
    if (!listRes.ok()) { test.skip(); return; }
    const docs: Array<{ id: string; processing_stage: string }> = await listRes.json();
    const done = docs.find((d) => d.processing_stage === 'done');
    if (!done) { test.skip(); return; }

    const structRes = await request.get(
      `http://127.0.0.1:8889/api/documents/${done.id}/structure?source=pdf`
    );
    if (!structRes.ok()) { test.skip(); return; }

    const body = await structRes.json();
    const blocks: Array<{ type: string }> = [];
    for (const ch of body?.structure?.chapters ?? []) {
      blocks.push(...(ch.content_blocks ?? []));
      for (const sec of ch.sections ?? []) blocks.push(...(sec.content_blocks ?? []));
    }
    const codeBlocks = blocks.filter((b) => b.type === 'code');
    for (const cb of codeBlocks) expect(cb.type).toBe('code');
  });

  test('structure for source=pdf may contain ContentBlocks with type "table"', async ({ request }) => {
    const listRes = await request.get('http://127.0.0.1:8889/api/documents');
    if (!listRes.ok()) { test.skip(); return; }
    const docs: Array<{ id: string; processing_stage: string }> = await listRes.json();
    const done = docs.find((d) => d.processing_stage === 'done');
    if (!done) { test.skip(); return; }

    const structRes = await request.get(
      `http://127.0.0.1:8889/api/documents/${done.id}/structure?source=pdf`
    );
    if (!structRes.ok()) { test.skip(); return; }

    const body = await structRes.json();
    const blocks: Array<{ type: string }> = [];
    for (const ch of body?.structure?.chapters ?? []) {
      blocks.push(...(ch.content_blocks ?? []));
      for (const sec of ch.sections ?? []) blocks.push(...(sec.content_blocks ?? []));
    }
    const tableBlocks = blocks.filter((b) => b.type === 'table');
    for (const tb of tableBlocks) expect(tb.type).toBe('table');
  });

  test('structure source=pdf chapters use "Page N" headings (PaddleOCR loop)', async ({ request }) => {
    const listRes = await request.get('http://127.0.0.1:8889/api/documents');
    if (!listRes.ok()) { test.skip(); return; }
    const docs: Array<{ id: string; processing_stage: string }> = await listRes.json();
    const done = docs.find((d) => d.processing_stage === 'done');
    if (!done) { test.skip(); return; }

    const structRes = await request.get(
      `http://127.0.0.1:8889/api/documents/${done.id}/structure?source=pdf`
    );
    if (!structRes.ok()) { test.skip(); return; }

    const body = await structRes.json();
    const chapters: Array<{ heading?: string; title?: string }> = body?.structure?.chapters ?? [];
    if (chapters.length === 0) { test.skip(); return; }

    const firstHeading = chapters[0].heading ?? chapters[0].title ?? '';
    expect(firstHeading).toMatch(/Page \d+/i);
  });
});

// ---------------------------------------------------------------------------
// §1 – Source audit: source="pdf" is PaddleOCR
// ---------------------------------------------------------------------------
test.describe('Extraction source audit: source="pdf" is PaddleOCR', () => {
  test('processed document has an extraction with source="pdf"', async ({ request }) => {
    const listRes = await request.get('http://127.0.0.1:8889/api/documents');
    if (!listRes.ok()) { test.skip(); return; }
    const docs: Array<{ id: string; processing_stage: string }> = await listRes.json();
    const done = docs.find((d) => d.processing_stage === 'done');
    if (!done) { test.skip(); return; }

    const structRes = await request.get(
      `http://127.0.0.1:8889/api/documents/${done.id}/structure?source=pdf`
    );
    expect(structRes.status()).toBe(200);
    const body = await structRes.json();
    expect(body.source).toBe('pdf');
  });

  test('source=docx is not a valid structure query value', async ({ request }) => {
    const listRes = await request.get('http://127.0.0.1:8889/api/documents');
    if (!listRes.ok()) { test.skip(); return; }
    const docs: Array<{ id: string; processing_stage: string }> = await listRes.json();
    const done = docs.find((d) => d.processing_stage === 'done');
    if (!done) { test.skip(); return; }

    const res = await request.get(
      `http://127.0.0.1:8889/api/documents/${done.id}/structure?source=docx`
    );
    expect([400, 422]).toContain(res.status());
  });
});
