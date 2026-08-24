import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { expect, test, type Page } from "@playwright/test";

const execFileAsync = promisify(execFile);

const accounts = [
  {
    role: "admin",
    email: "admin@demo.mobility.local",
    password: "DemoAdmin12345!",
  },
  {
    role: "advertiser",
    email: "advertiser@demo.mobility.local",
    password: "DemoAdvertiser12345!",
  },
  {
    role: "driver",
    email: "driver@demo.mobility.local",
    password: "DemoDriver12345!",
  },
] as const;

const notificationSetupScript = `
import asyncio
import os
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.models.notification import NotificationChannel, NotificationType
from app.models.user import User
from app.services.notifications import create_notification

accounts = {
    "admin": "admin@demo.mobility.local",
    "advertiser": "advertiser@demo.mobility.local",
    "driver": "driver@demo.mobility.local",
}

async def seed():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        for role, email in accounts.items():
            user = await session.scalar(select(User).where(User.email == email))
            if user is None:
                raise RuntimeError(f"missing demo persona: {email}")
            await create_notification(
                session,
                recipient_user_id=user.id,
                type_key=NotificationType.FRAUD_HOLD_RAISED,
                payload={
                    "fraud_flag_id": f"e2e:{role}",
                    "trip_session_id": f"e2e:{role}",
                },
                dedupe_key=f"e2e-notification-v1:{role}",
                channel=NotificationChannel.IN_APP,
            )
        await session.commit()
    await engine.dispose()

asyncio.run(seed())
`;

test.beforeAll(async () => {
  await execFileAsync(
    "docker",
    ["compose", "exec", "-T", "api", "python", "-c", notificationSetupScript],
    {
      cwd: "..",
      env: {
        ...process.env,
        // Compose requires this value while resolving the backend environment.
        PAYOUT_CRYPTO_KEYRING_B64:
          process.env.PAYOUT_CRYPTO_KEYRING_B64 ??
          '{"1":"AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="}',
      },
    },
  );
});

async function login(page: Page, account: (typeof accounts)[number]) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password").fill(account.password);
  await page.getByRole("button", { name: "Enter the network" }).click();
  await page.waitForURL(`**/${account.role}`);
}

for (const account of accounts) {
  test(`${account.role} sees the shared sanitized notification centre`, async ({ page }) => {
    await login(page, account);
    const trigger = page.getByRole("button", { name: /notifications/i });
    await expect(trigger).toBeVisible();
    await expect(trigger).toContainText(/\d+/);
    await trigger.click();
    await expect(page.getByRole("region", { name: "Notifications" })).toContainText(
      "Trip payment on hold",
    );
    await expect(page.getByRole("region", { name: "Notifications" })).not.toContainText(
      "fraud_flag_id",
    );
  });
}

test("advertiser changes the shared email preference while in-app stays mandatory", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "serialize the persistent preference mutation");
  await login(page, accounts[1]);
  await page.getByRole("button", { name: /notifications/i }).click();
  await expect(page.getByText("In-app notifications are always on.")).toBeVisible();
  const emailToggle = page.getByLabel("Transactional email");
  const expected = false;
  if ((await emailToggle.isChecked()) !== expected) {
    await emailToggle.click();
  }
  await expect(emailToggle).toBeChecked({ checked: expected });
  await page.reload();
  await page.getByRole("button", { name: /notifications/i }).click();
  await expect(page.getByLabel("Transactional email")).toBeChecked({ checked: expected });
  await expect(page.getByText("In-app notifications are always on.")).toBeVisible();
});
