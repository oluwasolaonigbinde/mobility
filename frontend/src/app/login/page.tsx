import type { Metadata } from "next";
import Link from "next/link";
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
        <p className="micro text-amber mb-3">Cardvert // aggregate mobility measurement</p>
        <h1 className="font-display text-4xl font-semibold tracking-tight">
          Mobility,
          <br />
          measured.
        </h1>
        <p className="text-muted mt-3 mb-8 text-sm">
          Sign in to your command center — campaigns, aggregate measurement, hourly earnings and
          fleet trust in one place.
        </p>

        <Panel className="p-6">
          <LoginForm demoLoginRole={demoLoginRole} />
        </Panel>

        <p className="text-muted mt-5 text-center text-sm">
          Want to drive with us?{" "}
          <Link href="/apply" className="text-amber hover:text-amber-soft transition-colors">
            Start an application →
          </Link>
        </p>

        <p className="micro text-faint mt-6 flex items-center gap-2">
          Terrax measurement · Abuja · Lagos · Port Harcourt · Kano
        </p>
      </div>
    </main>
  );
}
