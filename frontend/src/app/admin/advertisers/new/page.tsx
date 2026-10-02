import { CreateUserForm } from "../../users/new/create-user-form";
import { PageHeader } from "@/components/ui/page-header";
export default function AddCompany() {
  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Add company" eyebrow="Company details and its sign-in account" />
      <CreateUserForm fixedRole="advertiser" />
    </div>
  );
}
