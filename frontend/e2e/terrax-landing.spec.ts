import { expect, test } from "@playwright/test";

/**
 * The Terrax Media landing page is a static public marketing route: unlike the
 * rest of this suite it needs no backend, no seed and no session.
 */
const PATH = "/";
const COMPATIBILITY_PATH = "/landing";
const EMAIL = "terraxmediacompany@gmail.com";
const TERRAX_ASSETS = [
  "/brand/terrax/terrax-logo.png",
  "/brand/terrax/terrax-logo-white.png",
  "/marketing/terrax/hero-vehicle-placeholder.svg",
  "/marketing/terrax/fleet-corridor-placeholder.svg",
] as const;

function decodedAssetPath(responseUrl: string) {
  const url = new URL(responseUrl);
  if (url.pathname !== "/_next/image") return url.pathname;
  return url.searchParams.get("url") ?? "";
}

const VIEWPORTS = [
  { name: "mobile", width: 390, height: 844 },
  { name: "tablet", width: 834, height: 1112 },
  { name: "desktop", width: 1440, height: 900 },
];

for (const viewport of VIEWPORTS) {
  test(`no horizontal overflow at ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto(PATH);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBe(0);
  });
}

test("every call to action resolves", async ({ page }) => {
  await page.goto(PATH);

  const hrefs = await page
    .locator(".terrax-site a[href]")
    .evaluateAll((nodes) => nodes.map((node) => node.getAttribute("href") ?? ""));
  expect(hrefs.length).toBeGreaterThan(10);

  for (const href of hrefs) {
    if (href.startsWith("#")) {
      await expect(page.locator(href)).toHaveCount(1);
    } else if (href.startsWith("mailto:")) {
      expect(href.startsWith(`mailto:${EMAIL}`)).toBe(true);
    } else {
      expect(["/apply", "/login", "https://terraxmedia.com"]).toContain(href);
    }
  }
});

test("the legacy landing address redirects to the public root", async ({ page }) => {
  await page.goto(COMPATIBILITY_PATH);
  await expect(page).toHaveURL(/\/$/);
  await expect(page.locator(".terrax-site")).toBeVisible();
});

test("the mobile menu opens, navigates and closes", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(PATH);

  const toggle = page.getByRole("button", { name: /open menu/i });
  await toggle.click();

  const menu = page.locator("#primary-menu");
  await expect(menu).toBeVisible();

  await menu.getByRole("link", { name: "Contact" }).click();
  await expect(page.getByRole("button", { name: /open menu/i })).toHaveAttribute(
    "aria-expanded",
    "false",
  );
  await expect(menu).toHaveCount(0);
  await expect(page.locator("#contact")).toBeInViewport();
});

test("a shared deep link lands on its section, clear of the sticky header", async ({ page }) => {
  await page.goto(`${PATH}#contact`);

  const header = page.getByRole("banner");
  await expect(header).toBeVisible();
  const headerHeight = (await header.boundingBox())?.height ?? 0;

  await expect
    .poll(async () => {
      const box = await page.locator("#contact").boundingBox();
      return Math.round(box?.y ?? -1);
    })
    .toBeGreaterThanOrEqual(Math.round(headerHeight) - 1);

  const box = await page.locator("#contact").boundingBox();
  expect(box!.y).toBeLessThan(headerHeight + 40);
});

test("brand and driver paths resolve to their distinct entry points", async ({ page }) => {
  await page.goto(PATH);

  await expect(
    page.locator("#for-brands").getByRole("link", { name: "Advertise With Terrax" }),
  ).toHaveAttribute("href", new RegExp(`^mailto:${EMAIL}\\?`));
  await expect(
    page.locator("#for-drivers").getByRole("link", { name: "Become a Driver Partner" }),
  ).toHaveAttribute("href", "/apply");
});

test("reduced motion shows every section without animation", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(PATH);

  const reveals = page.locator(".terrax-reveal");
  const count = await reveals.count();
  expect(count).toBeGreaterThan(5);

  // Nothing below the fold has been scrolled into view, yet all of it is opaque.
  for (let i = 0; i < count; i += 1) {
    await expect(reveals.nth(i)).toHaveCSS("opacity", "1");
  }
});

test("the real logo assets load and none 404", async ({ page }) => {
  const failed: string[] = [];
  page.on("response", (response) => {
    const assetPath = decodedAssetPath(response.url());
    if (
      (assetPath.startsWith("/brand/terrax/") || assetPath.startsWith("/marketing/terrax/")) &&
      response.status() >= 400
    ) {
      failed.push(`${response.status()} ${response.url()}`);
    }
  });

  await page.goto(PATH);
  // Walk the page so the lazily loaded footer and report lockups are requested.
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForLoadState("networkidle");

  expect(failed).toEqual([]);
  const rendered = await page.locator(".terrax-site img").evaluateAll((nodes) =>
    nodes.map((node) => {
      const image = node as HTMLImageElement;
      return { source: image.currentSrc || image.src, naturalWidth: image.naturalWidth };
    }),
  );
  const paths = rendered.map(({ source }) => decodedAssetPath(source));
  expect(paths).toEqual(expect.arrayContaining([...TERRAX_ASSETS]));
  for (const image of rendered) expect(image.naturalWidth).toBeGreaterThan(0);
});
