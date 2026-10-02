import Link from "next/link";
import { PageHeader } from "@/components/ui/page-header";

export default function AdminHome() {
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Work queue" />
      <p className="text-muted mb-5">
        Use search to find a driver, car, campaign, company or staff login.
      </p>
      <nav aria-label="Admin directories" className="grid gap-3 sm:grid-cols-2">
        <Link className="border-edge rounded-xl border p-4" href="/admin/drivers">
          Drivers and cars
        </Link>
        <Link className="border-edge rounded-xl border p-4" href="/admin/campaigns">
          Campaigns
        </Link>
        <Link className="border-edge rounded-xl border p-4" href="/admin/advertisers">
          Companies
        </Link>
        <Link className="border-edge rounded-xl border p-4" href="/admin/settings/staff">
          Staff logins
        </Link>
      </nav>
    </div>
  );
}
