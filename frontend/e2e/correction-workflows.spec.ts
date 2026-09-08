import { expect, test, type Page } from "@playwright/test";

test.skip(process.env.P08_SYNTHETIC !== "1", "Explicit synthetic workflow fixture only");
const campaignId = "10000000-0000-4000-8000-000000000004";
async function uploads(page: Page, prefix: string) {
  const intents: Record<string, unknown>[] = [];
  await page.route(`**${prefix}/uploads`, async (route) => {
    intents.push(route.request().postDataJSON());
    const id = `00000000-0000-4000-8000-${String(intents.length).padStart(12, "0")}`;
    await route.fulfill({
      json: {
        upload_id: id,
        upload: { url: "http://localhost:3000/__synthetic-upload", fields: {} },
      },
    });
  });
  await page.route("**/__synthetic-upload", (route) => route.fulfill({ status: 204 }));
  await page.route(`**${prefix}/uploads/*/confirm`, (route) =>
    route.fulfill({ json: { id: route.request().url().split("/").at(-2), scan_status: "clean" } }),
  );
  await page.route("**/api/apply/onboarding/files/*/status", (route) =>
    route.fulfill({ json: { scan_status: "clean" } }),
  );
  return intents;
}
for (const stage of [
  {
    endpoint: "person-payee",
    button: "Submit person & payee evidence",
    fields: ["Driver licence", "Driver photo", "Signed agreement"],
    fileId: "driver_license_file_id",
  },
  {
    endpoint: "vehicle",
    button: "Submit vehicle evidence",
    fields: ["Vehicle registration", "Current insurance", "Vehicle photo"],
    fileId: "registration_file_id",
  },
]) {
  test(`${stage.endpoint} replacement after failure uploads the selected file`, async ({
    page,
  }) => {
    const intents = await uploads(page, "/api/apply/onboarding");
    const bodies: Record<string, unknown>[] = [];
    await page.route(`**/api/apply/onboarding/${stage.endpoint}`, async (route) => {
      bodies.push(route.request().postDataJSON());
      await route.fulfill(
        bodies.length < 3
          ? { status: 503, json: { error: { message: "Synthetic submission failure" } } }
          : { json: { status: "pending_review", version: 1 } },
      );
    });
    await page.goto("/apply");
    const form = page
      .locator("form")
      .filter({ has: page.getByRole("button", { name: stage.button, exact: true }) });
    await form.getByLabel("Onboarding access code").fill("first-access");
    for (const label of stage.fields)
      await form
        .getByLabel(label, { exact: true })
        .setInputFiles({ name: "same.png", mimeType: "image/png", buffer: Buffer.from("first") });
    await form.locator("button[type=submit]").click();
    await expect(form.getByRole("alert")).toContainText("Synthetic submission failure");
    expect(intents).toHaveLength(3);
    await form.locator("button[type=submit]").click();
    await expect.poll(() => bodies.length).toBe(2);
    expect(intents).toHaveLength(3);
    expect(bodies[1]).toEqual(bodies[0]);
    await form.getByLabel(stage.fields[0]!, { exact: true }).setInputFiles({
      name: "same.png",
      mimeType: "image/png",
      buffer: Buffer.from("replacement"),
    });
    await form.getByLabel("Onboarding access code").fill("second-access");
    await form.locator("button[type=submit]").click();
    await expect(form.getByRole("status")).toContainText("version 1");
    expect(intents).toHaveLength(6);
    expect(bodies[2]![stage.fileId]).not.toBe(bodies[0]![stage.fileId]);
    expect(bodies[2]!.application_access_token).toBe("second-access");
  });
}

test("campaign attachment recovery survives reload without another campaign", async ({
  page,
  context,
  request,
}) => {
  await request.post("http://127.0.0.1:38100/__test__/p08");
  await context.addCookies([
    {
      name: "mobility_session",
      value: "p08-advertiser",
      domain: "localhost",
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);
  await uploads(page, "/api/advertiser/files");
  await page.goto("/advertiser/campaigns/new");
  await page.getByLabel("Campaign name *").fill("Recovery campaign");
  await page.getByRole("button", { name: "Continue →" }).click();
  async function attach() {
    await page.getByRole("button", { name: "+ Add creative" }).click();
    await page.getByLabel("Creative name *").fill("Missing wrap");
    await page.getByLabel("Creative file *").setInputFiles({
      name: "wrap.png",
      mimeType: "image/png",
      buffer: Buffer.from("synthetic creative"),
    });
    await expect(page.getByText("wrap.png passed security scan", { exact: false })).toBeVisible();
    await page.getByRole("button", { name: "Continue →" }).click();
  }
  await attach();
  expect((await (await request.get("http://127.0.0.1:38100/__test__/p08")).json()).creates).toBe(0);
  await page.getByRole("button", { name: "Create campaign" }).click();
  await expect(page).toHaveURL(new RegExp(`campaignId=${campaignId}`));
  await expect(page.getByRole("button", { name: "Attach creatives" })).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Add creatives to Recovery campaign" }),
  ).toBeVisible();
  await expect(page.getByLabel("Campaign name *")).toHaveCount(0);
  await attach();
  await page.getByRole("button", { name: "Attach creatives" }).click();
  await expect(page).toHaveURL(`/advertiser/campaigns/${campaignId}`);
  await expect(page.getByText("Missing wrap", { exact: true })).toBeVisible();
  const result = await (await request.get("http://127.0.0.1:38100/__test__/p08")).json();
  expect(result).toEqual({ creates: 1, attempts: 2, creatives: 1 });
  await page.screenshot({ path: "test-results/correction-p08-campaign.png", fullPage: true });
});
