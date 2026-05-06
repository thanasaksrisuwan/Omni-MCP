import { expect, test } from "@playwright/test";

test("button story renders primary action", async ({ page }) => {
  await page.goto("/iframe.html?id=components-button--primary");
  await expect(page.getByRole("button", { name: "Save changes" })).toBeVisible();
});
