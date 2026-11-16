import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { getCurrentUser, roleHome } from "@/lib/auth/current-user";
import { Panel } from "@/components/ui/panel";
import { env } from "@/lib/env";
import { LoginBackdrop } from "./login-backdrop";
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
  const from = (await searchParams).from;
  const role = demoLoginRoleFromPath(from);
  const demoLoginRole = config.DEMO_LOGIN_ENABLED ? role : undefined;

  return (
    <main className="relative flex flex-1 items-center justify-center overflow-hidden bg-[#fbfcfa] p-6">
      <LoginBackdrop />

      <div className="animate-rise relative w-full max-w-sm">
        <p className="micro text-amber mb-3 font-semibold">Cardvert by Terrax Media</p>
        <h1 className="font-display text-4xl font-semibold tracking-tight">Sign in</h1>
        <p className="text-ink/80 mt-3 mb-8 text-sm font-medium">Welcome to Cardvert</p>

        <Panel className="p-6">
          <LoginForm
            demoLoginRole={demoLoginRole}
            from={typeof from === "string" ? from : undefined}
          />
        </Panel>

        <p className="text-muted mt-5 text-center text-sm">
          Want to drive with us?{" "}
          <Link href="/apply" className="text-amber hover:text-amber-soft transition-colors">
            Start an application →
          </Link>
        </p>

        <p className="micro text-faint mt-6 flex items-center gap-2">Terrax Media · Abuja</p>
      </div>
    </main>
  );
}
