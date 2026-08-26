import { expect, test, type Page } from "@playwright/test";

const ADMIN = {
  email: "admin@demo.mobility.local",
  password: "DemoAdmin12345!",
};

const assignmentId = process.env.SPOT_CHECK_ASSIGNMENT_ID;
const tripId = process.env.SPOT_CHECK_TRIP_ID;

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Enter the network" }).click();
  await page.waitForURL("**/admin");
}

test("ops queues a physical check and sends failure into the fraud hold", async ({ page }) => {
  test.skip(!assignmentId || !tripId, "synthetic assignment and trip IDs are required");
  test.setTimeout(60_000);
  await login(page);
  await page.goto("/admin/fraud");

  await page.getByLabel("Assignment ID").fill(assignmentId!);
  await page.getByLabel("Trip ID").fill(tripId!);
  await page
    .getByLabel("Why this physical check is needed")
    .fill("Synthetic in-person verification");
  await page.getByRole("button", { name: "Queue physical spot check" }).click();
  await expect(page.getByText("Physical spot check queued")).toBeVisible();

  const pending = page.getByText(`Assignment ${assignmentId!.slice(0, 8)}`).locator("..");
  await pending
    .getByLabel("Physical spot-check result note")
    .fill("Synthetic inspection found the display absent");
  await pending.getByRole("button", { name: "Fail and hold" }).click();
  await expect(pending).not.toBeVisible();
  await expect(page.getByText("Failed physical spot check")).toBeVisible();
});
