import { CreateUserForm } from "../../../users/new/create-user-form";
import { PageHeader } from "@/components/ui/page-header";
export default function AddStaff() {
  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Add staff login" eyebrow="Terrax staff only" />
      <CreateUserForm fixedRole="admin" />
    </div>
  );
}
