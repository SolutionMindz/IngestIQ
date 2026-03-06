import { test, expect } from '@playwright/test';

test.describe('Navigation', () => {
  test('shows app header and can navigate to Users', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: /Knowledge Ingestion Admin Console/i })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Users' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Review' })).toBeVisible();

    await page.getByRole('link', { name: 'Users' }).click();
    await expect(page).toHaveURL(/\/users/);
  });

  test('can navigate back to Dashboard', async ({ page }) => {
    await page.goto('/users');
    await page.getByRole('link', { name: 'Dashboard' }).click();
    await expect(page).toHaveURL(/\/$/);
  });
});
