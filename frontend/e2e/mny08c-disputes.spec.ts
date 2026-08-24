import { expect, test, type Page } from "@playwright/test";

async function login(page: Page, email: string, password: string, destination: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Enter the network" }).click();
  await page.waitForURL(`**/${destination}`);
}

async function disputableSeedHold(page: Page): Promise<{ id: string; tripId: string }> {
  const cookieName = process.env.SESSION_COOKIE_NAME ?? "mobility_session";
  const session = (await page.context().cookies()).find((cookie) => cookie.name === cookieName);
  expect(session, `login must set the ${cookieName} session cookie`).toBeTruthy();
  const apiBase = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";
  const response = await page.request.get(`${apiBase}/api/v1/driver/fraud-holds`, {
    headers: { Authorization: `Bearer ${session!.value}` },
  });
  expect(response.ok(), "the deterministic rich-seed hold fixture must be readable").toBe(true);
  const payload = (await response.json()) as {
    items: Array<{ id: string; trip_session_id: string; public_status: string; dispute: object | null }>;
  };
  const hold = payload.items.find(
    (item) => item.public_status !== "review_cleared" && item.dispute === null,
  );
  if (!hold) throw new Error("The deterministic project driver has no disputable held trip");
  return { id: hold.id, tripId: hold.trip_session_id };
}

test("driver dispute and staff reply persist across the isolated cross-role flow", async ({
  page,
}, testInfo) => {
  const driver =
    testInfo.project.name === "mobile-chrome"
      ? { email: "driver02@demo.mobility.local", password: "DemoDriver02Pass!" }
      : { email: "driver01@demo.mobility.local", password: "DemoDriver01Pass!" };
  await login(page, driver.email, driver.password, "driver");
  const seedHold = await disputableSeedHold(page);
  const tripUrl = `/driver/earnings/trips/${seedHold.tripId}`;
  await page.goto(tripUrl);
  const hold = page.getByTestId(`driver-fraud-hold-${seedHold.id}`);
  await expect(hold.getByRole("button", { name: "Submit dispute" })).toBeVisible();

  const message = `Please review the MNY-08C ${testInfo.project.name} route fixture.`;
  await hold.getByLabel("Dispute message").fill(message);
  await hold.getByRole("button", { name: "Submit dispute" }).click();
  await expect(hold.getByText(message)).toBeVisible();
  await expect(hold.getByText("Awaiting reply")).toBeVisible();
  await expect(hold).not.toContainText(/Detection evidence|fingerprint|matched trip/i);

  await page.context().clearCookies();
  await login(page, "admin@demo.mobility.local", "DemoAdmin12345!", "admin");
  await page.goto("/admin/fraud");
  const dispute = page
    .getByTestId(`fraud-flag-${seedHold.id}`)
    .getByRole("region", { name: "Driver dispute" });
  await expect(dispute).toBeVisible();
  const reply = "We reviewed your route details and recorded the outcome.";
  await dispute.getByLabel("Reply to driver").fill(reply);
  await dispute.getByRole("button", { name: "Send reply" }).click();
  await expect(dispute.getByText(reply)).toBeVisible();

  await page.context().clearCookies();
  await login(page, driver.email, driver.password, "driver");
  await page.goto(tripUrl);
  const reloadedHold = page.getByTestId(`driver-fraud-hold-${seedHold.id}`);
  await expect(reloadedHold.getByText(message)).toBeVisible();
  await expect(reloadedHold.getByText(reply)).toBeVisible();
  await expect(reloadedHold.getByText("Staff replied", { exact: true })).toBeVisible();
});
