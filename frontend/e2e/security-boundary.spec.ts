import { expect, test } from "@playwright/test";

test("deployed edge enforces the browser security policy without disabling driver capabilities", async ({
  context,
  page,
  request,
}, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "one deployed-edge policy check is sufficient");

  const response = await request.get("/login");
  expect(response.ok()).toBe(true);
  expect(response.headers()["x-frame-options"]).toBe("DENY");

  const csp = response.headers()["content-security-policy"];
  expect(csp).toContain("default-src 'self'");
  expect(csp).toContain("frame-ancestors 'none'");
  expect(csp).toContain("worker-src 'self' blob:");
  expect(csp).toContain("manifest-src 'self'");
  expect(csp).not.toContain("'unsafe-eval'");
  expect(csp).toContain("style-src 'self'; style-src-attr 'unsafe-inline'");

  const permissions = response.headers()["permissions-policy"];
  expect(permissions).toContain("camera=()");
  expect(permissions).toContain("microphone=()");
  expect(permissions).toContain("geolocation=(self)");
  expect(permissions).toContain("screen-wake-lock=(self)");
  expect(permissions).toContain("clipboard-write=(self)");

  const origin = new URL(response.url()).origin;
  const cdp = await context.newCDPSession(page);
  await cdp.send("Browser.grantPermissions", {
    origin,
    permissions: ["geolocation", "wakeLockScreen"],
  });
  await context.grantPermissions(["geolocation"], { origin });
  await context.setGeolocation({ latitude: 9.0765, longitude: 7.3986 });
  await page.goto("/login");
  const capabilities = await page.evaluate(async () => {
    const geolocation = await new Promise<boolean>((resolve) =>
      navigator.geolocation.getCurrentPosition(
        () => resolve(true),
        () => resolve(false),
        { timeout: 5_000 },
      ),
    );
    let wakeLock = false;
    try {
      const wake = await Promise.race([
        navigator.wakeLock.request("screen"),
        new Promise<never>((_, reject) =>
          setTimeout(() => reject(new Error("wake-lock timeout")), 5_000),
        ),
      ]);
      wakeLock = !wake.released;
      await wake.release();
    } catch {
      wakeLock = false;
    }
    const registration = await navigator.serviceWorker.register("/driver-sw.js", {
      scope: "/driver",
    });
    const serviceWorker = Boolean(
      registration.active || registration.installing || registration.waiting,
    );
    await registration.unregister();
    return {
      clipboard: typeof navigator.clipboard?.writeText === "function",
      geolocation,
      serviceWorker,
      wakeLock,
    };
  });
  expect(capabilities).toMatchObject({
    clipboard: true,
    geolocation: true,
    serviceWorker: true,
  });
  if (process.env.R14_REQUIRE_WAKE_LOCK === "1") expect(capabilities.wakeLock).toBe(true);

  const manifest = await request.get("/driver/manifest.webmanifest");
  expect(manifest.ok()).toBe(true);
  expect(manifest.headers()["content-type"]).toContain("application/manifest+json");
  expect((await request.get("/driver-sw.js")).ok()).toBe(true);

  const blockedRequests: string[] = [];
  const blockedFailures: string[] = [];
  page.on("request", (outgoing) => {
    if (outgoing.url().startsWith("https://attacker.invalid")) blockedRequests.push(outgoing.url());
  });
  page.on("requestfailed", (outgoing) => {
    if (outgoing.url().startsWith("https://attacker.invalid")) {
      blockedFailures.push(outgoing.failure()?.errorText ?? "");
    }
  });
  const blockedLoads = await page.evaluate(async () => {
    const connect = fetch("https://attacker.invalid/connect").then(
      () => false,
      () => true,
    );
    const image = new Promise<boolean>((resolve) => {
      const element = new Image();
      element.onload = () => resolve(false);
      element.onerror = () => resolve(true);
      element.src = "https://attacker.invalid/image.png";
    });
    const script = new Promise<boolean>((resolve) => {
      const element = document.createElement("script");
      element.onload = () => resolve(false);
      element.onerror = () => resolve(true);
      element.src = "https://attacker.invalid/script.js";
      document.head.append(element);
    });
    return Promise.all([connect, image, script]);
  });
  expect(blockedLoads).toEqual([true, true, true]);
  await expect.poll(() => blockedFailures.length).toBe(blockedRequests.length);
  expect(blockedFailures.every(Boolean)).toBe(true);

  await page.setContent('<iframe title="blocked-frame" src="/login"></iframe>');
  await expect
    .poll(() => page.frames().some((frame) => frame !== page.mainFrame() && frame.url().endsWith("/login")))
    .toBe(false);
});

test("edge policy covers frontend, API, redirect, not-found and failure responses", async ({
  request,
}, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "one deployed-edge response matrix is sufficient");
  test.skip(process.env.R14_DEPLOYED_EDGE_PROBE !== "1", "requires the disposable API oracle");

  for (const [path, status] of [
    ["/login", 200],
    ["/health", 200],
    ["/api/v1/health/redirect", 302],
    ["/__r14_missing__", 404],
    ["/api/v1/health/fail", 500],
  ] as const) {
    const response = await request.get(path, { maxRedirects: 0 });
    expect(response.status(), path).toBe(status);
    expect(response.headers()["content-security-policy"], path).toContain("default-src 'self'");
    expect(response.headers()["x-frame-options"], path).toBe("DENY");
    expect(response.headers()["permissions-policy"], path).toContain("geolocation=(self)");
  }
});

test("narrower script policy demonstrably blocks the built Next bootstrap", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "one CSP relaxation oracle is sufficient");
  const violations: string[] = [];
  page.on("console", (message) => {
    if (/content security policy|violat/i.test(message.text())) violations.push(message.text());
  });
  await page.route("**/login", async (route) => {
    const response = await route.fetch();
    const headers = response.headers();
    const policy = headers["content-security-policy"];
    if (!policy) throw new Error("deployed response is missing Content-Security-Policy");
    headers["content-security-policy"] = policy.replace(
      "script-src 'self' 'unsafe-inline'",
      "script-src 'self'",
    );
    await route.fulfill({ response, headers });
  });

  await page.goto("/login");
  await expect.poll(() => violations.some((message) => message.includes("script-src"))).toBe(true);
});

test("deployed Next server rejects a cross-origin Server Action", async ({
  page,
  request,
}, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "one deployed-edge origin check is sufficient");

  await page.goto("/login");
  let actionRequest: { body: Buffer; headers: Record<string, string> } | undefined;
  page.on("request", (outgoing) => {
    if (outgoing.method() !== "POST" || !outgoing.url().endsWith("/login")) return;
    const body = outgoing.postDataBuffer();
    if (body) actionRequest = { body, headers: outgoing.headers() };
  });
  await page.getByLabel("Email").fill("r14-origin-probe@example.invalid");
  await page.getByLabel("Password").fill("WrongPassword123!");
  const sameOriginResponsePromise = page.waitForResponse(
    (response) => response.request().method() === "POST" && response.url().endsWith("/login"),
  );
  await page.getByRole("button", { name: "Enter the network" }).click();
  const sameOriginResponse = await sameOriginResponsePromise;
  expect(sameOriginResponse.status()).toBeLessThan(500);
  expect(actionRequest).toBeDefined();

  const replayHeaders: Record<string, string> = {
    ...actionRequest!.headers,
    origin: "https://attacker.invalid",
  };
  delete replayHeaders["content-length"];
  delete replayHeaders.host;
  const crossOriginResponse = await request.fetch("/login", {
    method: "POST",
    headers: replayHeaders,
    data: actionRequest!.body,
  });
  expect([400, 403, 500]).toContain(crossOriginResponse.status());
  expect(crossOriginResponse.status()).not.toBe(sameOriginResponse.status());
});

test("successful production login sets the host-only hardened session cookie", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "one cookie contract check is sufficient");
  const email = process.env.R14_SECURITY_LOGIN_EMAIL;
  const password = process.env.R14_SECURITY_LOGIN_PASSWORD;
  test.skip(!email || !password, "requires synthetic local login authority");

  await page.goto("/login");
  await page.getByLabel("Email").fill(email!);
  await page.getByLabel("Password").fill(password!);
  await page.getByRole("button", { name: "Enter the network" }).click();
  await page.waitForURL((url) => url.pathname !== "/login");
  const cookie = (await page.context().cookies()).find(
    (value) => value.name === "__Host-cardvert_session",
  );

  expect(cookie).toMatchObject({
    httpOnly: true,
    secure: true,
    sameSite: "Lax",
    path: "/",
  });
  expect(cookie?.domain).toBe("localhost");
});

test("cold production login keeps known-wrong and unknown identities timing-equivalent", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "one production timing oracle is sufficient");
  const knownEmail = process.env.R14_TIMING_KNOWN_EMAIL;
  test.skip(process.env.R14_TIMING_ORACLE !== "1" || !knownEmail, "requires a cold disposable API");

  const schedule: boolean[] = [];
  let randomState = 0x14c0ffee;
  for (let pair = 0; pair < 12; pair += 1) {
    randomState = (randomState * 1_664_525 + 1_013_904_223) >>> 0;
    const unknownFirst = pair === 0 || (randomState & 1) === 1;
    schedule.push(unknownFirst, !unknownFirst);
  }

  const knownDurations: number[] = [];
  const unknownDurations: number[] = [];
  await page.goto("/login");
  await page.getByLabel("Email").fill(knownEmail!);
  await page.getByLabel("Password").fill("R14-Wrong-Password-Only!");
  const warmResponsePromise = page.waitForResponse(
    (response) => response.request().method() === "POST" && response.url().endsWith("/login"),
  );
  await page.getByRole("button", { name: "Enter the network" }).click();
  expect((await warmResponsePromise).status()).toBe(200);
  await expect(
    page.getByText("Invalid email or password, or the account is not active.", { exact: true }),
  ).toBeVisible();
  for (const [attempt, unknown] of schedule.entries()) {
    const responsePromise = page.waitForResponse(
      (response) => response.request().method() === "POST" && response.url().endsWith("/login"),
    );
    await page
      .getByLabel("Email")
      .fill(unknown ? `r14-timing-${attempt}@example.com` : knownEmail!);
    await page.getByLabel("Password").fill("R14-Wrong-Password-Only!");
    const started = performance.now();
    await page.getByRole("button", { name: "Enter the network" }).click();
    const response = await responsePromise;
    const duration = performance.now() - started;
    expect(response.status()).toBe(200);
    await expect(
      page.getByText("Invalid email or password, or the account is not active.", { exact: true }),
    ).toBeVisible();
    (unknown ? unknownDurations : knownDurations).push(duration);
  }

  const trimmedMean = (values: number[]) => {
    const sorted = [...values].sort((left, right) => left - right).slice(1, -1);
    return sorted.reduce((total, value) => total + value, 0) / sorted.length;
  };
  const p95 = (values: number[]) => {
    const sorted = [...values].sort((left, right) => left - right);
    return sorted[Math.ceil(sorted.length * 0.95) - 1]!;
  };
  for (const ratio of [
    trimmedMean(unknownDurations) / trimmedMean(knownDurations),
    p95(unknownDurations) / p95(knownDurations),
  ]) {
    expect(ratio).toBeGreaterThanOrEqual(0.8);
    expect(ratio).toBeLessThanOrEqual(1.25);
  }
});
