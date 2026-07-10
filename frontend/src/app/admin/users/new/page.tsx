import type { Metadata } from "next";
import Link from "next/link";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { CreateUserForm } from "./create-user-form";

export const metadata: Metadata = { title: "Create user" };

export default function NewUserPage() {
  return (
    <div className="animate-rise mx-auto max-w-2xl">
      <nav aria-label="Breadcrumb" className="micro text-faint mb-4">
        <Link href="/admin/users" className="hover:text-muted">
          Users
        </Link>{" "}
        / <span className="text-muted">Create</span>
      </nav>
      <PageHeader
        title="Create user"
        eyebrow="Onboarding is operator-led — you set the account up, they sign in"
      />
      <Panel className="p-6 md:p-8">
        <CreateUserForm />
      </Panel>
    </div>
  );
}
