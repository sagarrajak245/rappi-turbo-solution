import { expect, test } from "@playwright/test";

const BUYER = { email: "sagar@rappi.test", password: process.env.E2E_BUYER_PASSWORD ?? "dev-buyer-password" };

test("buyer signs in, runs the agent, opens the run, and cannot see admin", async ({ page }) => {
  await page.goto("/inbox");
  await expect(page).toHaveURL(/\/login/);

  await page.getByPlaceholder("Email").fill(BUYER.email);
  await page.getByPlaceholder("Password").fill(BUYER.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login/);

  await page.goto("/inbox");
  await expect(page.getByRole("heading", { name: "Inbox" })).toBeVisible();
  const row = page.getByRole("row").filter({ hasText: "BANDRA" }).first();
  await expect(row).toBeVisible();

  // Start a run unless one is already waiting, then open it from the inbox.
  const runAgent = row.getByRole("button", { name: "Run agent" });
  if (await runAgent.isVisible()) await runAgent.click();
  const open = row.getByRole("link", { name: /Review|Open/ });
  await expect(open).toBeVisible({ timeout: 45_000 });
  await open.click();

  // next dev compiles each route on first visit
  await expect(page).toHaveURL(/\/runs\//, { timeout: 30_000 });
  await expect(page.getByText("In short")).toBeVisible({ timeout: 30_000 });

  await page.goto("/admin");
  await expect(page.getByText("Total runs")).toHaveCount(0);
  await expect(page.getByText(/your role cannot do this/i).first()).toBeVisible({ timeout: 30_000 });
});
