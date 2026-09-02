import { redirect } from "next/navigation";
import { ChangePasswordForm } from "@/components/auth/change-password-form";
import { SessionLogoutButton } from "@/components/driver/logout-button";
import { Panel } from "@/components/ui/panel";
import { getCurrentUser, roleHome } from "@/lib/auth/current-user";

export default async function DriverChangePasswordPage() {
  const me = await getCurrentUser();
  if (!me) redirect("/login");
  if (me.user.role !== "driver") redirect(roleHome(me.user.role));
  if (!me.user.must_change_password) redirect("/driver");

  return (
    <main className="bg-bg flex min-h-screen items-center justify-center px-5 py-10">
      <Panel className="w-full max-w-md p-7">
        <p className="micro text-cyan mb-2">Driver account</p>
        <h1 className="mb-2 text-2xl font-semibold">Secure your account</h1>
        <p className="text-muted mb-6 text-sm">Set your own password before starting a trip.</p>
        <ChangePasswordForm />
        <div className="mt-5 flex justify-center">
          <SessionLogoutButton
            label="Sign out"
            className="micro text-muted hover:text-coral transition-colors"
          />
        </div>
      </Panel>
    </main>
  );
}
