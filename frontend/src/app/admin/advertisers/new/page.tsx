import { CreateCompanyForm } from "./create-company-form";
import { PageHeader } from "@/components/ui/page-header";
export default function AddCompany() {
  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Add company" eyebrow="Company details and its login invite" />
      <CreateCompanyForm />
    </div>
  );
}
export const metadata = { title: "New advertiser" };
