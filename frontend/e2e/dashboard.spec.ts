import { test, expect } from '@playwright/test';

test.describe('Dashboard', () => {
  test('shows document intake panel and select document controls', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: /Knowledge Ingestion Admin Console/i })).toBeVisible();

    // Dashboard shows document intake panel heading
    await expect(
      page.getByRole('heading', { name: /Document Intake Panel/i })
    ).toBeVisible({ timeout: 15_000 });
  });

  test('document intake has drop zone or document selector', async ({ page }) => {
    await page.goto('/');
    const intakeHeading = page.getByRole('heading', { name: /Document Intake Panel/i });
    await expect(intakeHeading).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByText(/Drag & drop .docx or .pdf here/i).first()
    ).toBeVisible();
  });
});
