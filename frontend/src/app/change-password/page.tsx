import { redirect } from "next/navigation";
import Link from "next/link";
import { ChangePasswordForm } from "@/components/auth/change-password-form";
import { SessionLogoutButton } from "@/components/driver/logout-button";
import { Panel } from "@/components/ui/panel";
import { getCurrentUser, roleHome } from "@/lib/auth/current-user";

export default async function ChangePasswordPage() {
  const me = await getCurrentUser();
  if (!me) redirect("/login");
  if (me.user.role === "driver") redirect("/driver/change-password");

  return (
    <main className="flex min-h-screen items-center justify-center px-5 py-10">
      <Panel className="w-full max-w-md p-7">
        <p className="micro text-amber mb-2">Account security</p>
        <h1 className="mb-2 text-2xl font-semibold">Change password</h1>
        <p className="text-muted mb-6 text-sm">
          {me.user.must_change_password
            ? "Replace the temporary password before continuing."
            : "Choose a password you don’t use anywhere else."}
        </p>
        <ChangePasswordForm />
        {!me.user.must_change_password ? (
          <Link className="text-green mt-5 block text-sm underline" href={roleHome(me.user.role)}>
            Back to Cardvert
          </Link>
        ) : null}
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
