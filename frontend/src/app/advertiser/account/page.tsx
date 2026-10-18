import Link from "next/link";
import { requireRole } from "@/lib/auth/current-user";
import { ChangePasswordForm } from "@/components/auth/change-password-form";
import { SessionLogoutButton } from "@/components/driver/logout-button";
import { Panel } from "@/components/ui/panel";

export const metadata = { title: "Account" };

export default async function AccountPage() {
  const me = await requireRole("advertiser");
  return (
    <div className="mx-auto grid max-w-3xl gap-6">
      <h1 className="font-display text-3xl font-semibold">Your account</h1>
      <Panel className="p-6">
        <h2 className="font-display text-xl font-semibold">Company details</h2>
        <p className="text-muted mt-2">{me.advertiser_organization?.name}</p>
        <Link href="/advertiser/company" className="brand-secondary mt-4">
          View company details →
        </Link>
      </Panel>
      <Panel className="scroll-mt-24 p-6" id="people">
        <h2 className="font-display text-xl font-semibold">People</h2>
        <p className="mt-4 font-semibold">{me.user.full_name}</p>
        <p className="text-muted mt-1 text-sm break-words">{me.user.email}</p>
        <p className="text-muted mt-2 text-sm">Your sign-in</p>
      </Panel>
      <Panel className="scroll-mt-24 p-6" id="password">
        <h2 className="font-display mb-5 text-xl font-semibold">Change password</h2>
        <ChangePasswordForm />
      </Panel>
      <SessionLogoutButton label="Sign out" className="brand-secondary" />
    </div>
  );
}
