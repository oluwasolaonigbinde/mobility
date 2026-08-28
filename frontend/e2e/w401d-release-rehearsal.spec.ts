import { expect, test, type BrowserContext } from "@playwright/test";

const heldTrip = "20000000-0000-4000-8000-000000000006";

async function installSession(context: BrowserContext, token: string) {
  await context.addCookies([
    {
      name: "mobility_session",
      value: token,
      url: "http://127.0.0.1:34101",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);
}

test("W4-01D history, hold, dispute, outcome and fail-safe PWA rehearsal", async ({
  context,
  page,
  request,
}, testInfo) => {
  const scope = testInfo.project.name;
  await installSession(context, `w401d-driver-${scope}`);

  await page.goto("/driver/assignments");
  await expect(page.getByText("Lagos Release Rehearsal").first()).toBeVisible();
  await expect(page.getByText("Completed", { exact: true }).first()).toBeVisible();

  await page.goto("/driver/earnings");
  await expect(page.getByText(/Recent page: 1 held/)).toBeVisible();
  await expect(page.getByText("Held", { exact: true })).toBeVisible();
  await expect(page.getByText("Debt carried", { exact: true })).toBeVisible();
  await expect(page.getByText("Voided", { exact: true }).first()).toBeVisible();

  await page.getByRole("link", { name: /Lagos Release Rehearsal.*1,250\.00.*Held/s }).click();
  await expect(page).toHaveURL(new RegExp(`/driver/earnings/trips/${heldTrip}$`));
  await expect(page.getByText("Payout v3 · frozen base/premium terms")).toBeVisible();
  await expect(page.getByText("Route pattern needs review")).toBeVisible();

  const message = "My signal dropped near the bridge; please review this trip.";
  await page.getByLabel("Dispute message").fill(message);
  await page.getByRole("button", { name: "Submit dispute" }).click();
  await expect
    .poll(async () => {
      const result = await request.get(`http://127.0.0.1:38101/__test__/state?scope=${scope}`);
      return (await result.json()).disputeRequests;
    })
    .toBe(1);
  await page.reload();
  await expect(page.getByText(message)).toBeVisible();
  await expect(page.getByText("Awaiting reply")).toBeVisible();

  const resolution = await request.post("http://127.0.0.1:38101/__test__/resolve", {
    data: { scope },
  });
  expect(resolution.ok()).toBeTruthy();
  await page.reload();
  await expect(page.getByText("Review cleared")).toBeVisible();
  await expect(
    page.getByText("We reviewed the trip and cleared the earnings review."),
  ).toBeVisible();
  await page.getByRole("button", { name: /Notifications/ }).click();
  await expect(page.getByText("Staff completed their review of a trip.")).toBeVisible();

  await page.goto("/driver/earnings");
  await expect(page.getByText(/Recent page: 0 held/)).toBeVisible();
  await expect(page.getByText(/Recent page:.*2 released/)).toBeVisible();
  await page.reload();
  await expect(page.getByText(/Recent page: 0 held/)).toBeVisible();

  const manifest = await request.get("/driver/manifest.webmanifest");
  expect(manifest.ok()).toBeTruthy();
  expect(await manifest.json()).toMatchObject({
    name: "Cardvert Driver",
    start_url: "/driver",
    scope: "/driver",
    display: "standalone",
  });

  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller)
      await new Promise((resolve) => setTimeout(resolve, 250));
  });
  await page.reload();
  const cachedUrls = await page.evaluate(async () => {
    const keys = await caches.keys();
    const requests = (
      await Promise.all(keys.map((key) => caches.open(key).then((cache) => cache.keys())))
    ).flat();
    return requests.map((entry) => new URL(entry.url).pathname);
  });
  expect(cachedUrls.length).toBeGreaterThan(0);
  expect(cachedUrls.every((path) => path.startsWith("/_next/static/"))).toBeTruthy();

  if (testInfo.project.name === "chromium") {
    await context.setOffline(true);
    await expect(page.getByText(/Recent page:/)).toHaveCount(0);
    await expect(page.getByText("Current earnings hidden while offline")).toBeVisible();
    await context.setOffline(false);
    await expect(page.getByText(/Recent page:/)).toHaveCount(0);
    await expect(page.getByText("Current earnings hidden while offline")).toBeVisible();
    await page.reload();
    await expect(page.getByText(/Recent page: 0 held/)).toBeVisible();

    await context.setOffline(true);
    await page.goto("/driver/earnings");
    await expect(
      page.getByText("Fresh earnings and review details are unavailable."),
    ).toBeVisible();
    await expect(page.getByText(/₦1,250/)).toHaveCount(0);
    await expect(page.getByLabel("Dispute message")).toHaveCount(0);
    const offlineMutation = await page.evaluate(async () => {
      try {
        await fetch("/api/notifications/read-all", { method: "POST" });
        return "unexpected-success";
      } catch {
        return "blocked";
      }
    });
    expect(offlineMutation).toBe("blocked");
    await context.setOffline(false);
  } else {
    expect(page.viewportSize()?.width).toBeLessThanOrEqual(400);
  }
  const stateResponse = await request.get(`http://127.0.0.1:38101/__test__/state?scope=${scope}`);
  expect(await stateResponse.json()).toMatchObject({ disputeRequests: 1, resolved: true });

  await installSession(context, `w401d-revoked-${scope}`);
  await page.goto("/driver/earnings");
  await expect(page).toHaveURL(/\/login/);
  await page.goBack();
  await expect(page.getByText(/Recent page:/)).toHaveCount(0);

  await installSession(context, `w401d-wrong-role-${scope}`);
  await page.goto("/driver/earnings");
  await expect(page).toHaveURL(/\/advertiser/);
  await expect(page.getByText(/Recent page:/)).toHaveCount(0);
});
