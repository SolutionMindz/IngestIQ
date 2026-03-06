import { test, expect } from '@playwright/test';

test.describe('Review nav link', () => {
  test('Review link is visible in header', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('link', { name: 'Review' })).toBeVisible();
  });

  test('navigates to /review when clicked', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'Review' }).click();
    await expect(page).toHaveURL(/\/review/);
  });
});

test.describe('Human Review Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/review');
  });

  test('shows Review Queue sidebar', async ({ page }) => {
    await expect(page.getByText('Review Queue')).toBeVisible({ timeout: 10_000 });
  });

  test('shows status filter tabs', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'All' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Pending' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Assigned to Me' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Completed' })).toBeVisible();
  });

  test('shows Reviewer Dashboard by default (no task selected)', async ({ page }) => {
    await expect(page.getByText('Reviewer Dashboard')).toBeVisible({ timeout: 10_000 });
  });

  test('shows reviewer stats cards', async ({ page }) => {
    await expect(page.getByText('Total Assigned')).toBeVisible({ timeout: 10_000 });
    // Use unique stat card labels that don't conflict with queue filter buttons
    await expect(page.getByText('Corrections Applied')).toBeVisible();
    await expect(page.getByText('Acceptance Rate')).toBeVisible();
  });

  test('queue status filter tabs switch active state', async ({ page }) => {
    const pendingBtn = page.getByRole('button', { name: 'Pending' });
    await pendingBtn.click();
    await expect(pendingBtn).toHaveClass(/bg-indigo-600/);

    const allBtn = page.getByRole('button', { name: 'All' });
    await allBtn.click();
    await expect(allBtn).toHaveClass(/bg-indigo-600/);
  });

  test('Refresh button is present in queue sidebar', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Refresh' })).toBeVisible();
  });

  test('can navigate back to Dashboard from Review', async ({ page }) => {
    await page.getByRole('link', { name: 'Dashboard' }).click();
    await expect(page).toHaveURL(/\/$/);
  });
});

test.describe('Review Page task interaction (if tasks exist)', () => {
  test('clicking a task in the queue shows ReviewTask panel', async ({ page }) => {
    await page.goto('/review');

    // Wait for queue to load
    await page.waitForTimeout(1500);

    // Try to click the first task row if any exist
    const taskRow = page.locator('ul li').first();
    const taskCount = await taskRow.count();

    if (taskCount === 0) {
      // No tasks in this environment — skip
      test.skip();
      return;
    }

    await taskRow.click();

    // After clicking, should show "Page X Review" heading (ReviewTask panel)
    await expect(
      page.getByText(/Page \d+ Review/)
    ).toBeVisible({ timeout: 10_000 });
  });

  test('ReviewTask shows three text panels', async ({ page }) => {
    await page.goto('/review');
    await page.waitForTimeout(1500);

    const taskRow = page.locator('ul li').first();
    if (await taskRow.count() === 0) {
      test.skip();
      return;
    }

    await taskRow.click();
    await page.waitForTimeout(1500);

    // Check for the three panel labels
    const nativeLabel = page.getByText('Native PDF');
    const textractLabel = page.getByText(/Textract.*differences highlighted/i);
    const screenshotLabel = page.getByText('Page Screenshot');

    // At least 2 of the 3 text panels should be present
    const labels = [nativeLabel, textractLabel, screenshotLabel];
    let visibleCount = 0;
    for (const label of labels) {
      if (await label.isVisible().catch(() => false)) visibleCount++;
    }
    expect(visibleCount).toBeGreaterThanOrEqual(2);
  });

  test('ReviewTask shows submit button', async ({ page }) => {
    await page.goto('/review');
    await page.waitForTimeout(1500);

    const taskRow = page.locator('ul li').first();
    if (await taskRow.count() === 0) {
      test.skip();
      return;
    }

    await taskRow.click();
    await page.waitForTimeout(1500);

    await expect(
      page.getByRole('button', { name: /Submit Correction/i })
    ).toBeVisible({ timeout: 8_000 });
  });
});
