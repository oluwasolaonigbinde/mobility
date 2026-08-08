import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { getCurrentUser, roleHome } from "@/lib/auth/current-user";
import { Panel } from "@/components/ui/panel";
import { env } from "@/lib/env";
import { LoginForm } from "./login-form";
import { demoLoginRoleFromPath } from "./demo-role";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ from?: string | string[] }>;
}) {
  const me = await getCurrentUser();
  if (me) {
    redirect(roleHome(me.user.role));
  }
  const config = env();
  const role = demoLoginRoleFromPath((await searchParams).from);
  const demoLoginRole = config.DEMO_LOGIN_ENABLED ? role : undefined;

  return (
    <main className="bg-atmosphere relative flex flex-1 items-center justify-center overflow-hidden p-6">
      <div className="bg-grid pointer-events-none absolute inset-0" aria-hidden />

      <div className="animate-rise relative w-full max-w-sm">
        <p className="micro text-amber mb-3">Vantage // urban attention network</p>
        <h1 className="font-display text-4xl font-semibold tracking-tight">
          Urban attention,
          <br />
          measured.
        </h1>
        <p className="text-muted mt-3 mb-8 text-sm">
          Sign in to your command center — campaigns, live analytics, earnings and fleet trust in
          one place.
        </p>

        <Panel className="p-6">
          <LoginForm demoLoginRole={demoLoginRole} />
        </Panel>

        <p className="micro text-faint mt-6 flex items-center gap-2">
          <span
            className="animate-pulse-dot bg-green inline-block size-1.5 rounded-full"
            aria-hidden
          />
          Network live · Abuja · Lagos · Port Harcourt · Kano
        </p>
      </div>
    </main>
  );
}
