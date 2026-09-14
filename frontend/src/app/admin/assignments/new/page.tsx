import { PageHeader } from "@/components/ui/page-header";
import { AssignmentForm } from "./assignment-form";
export const metadata = { title: "Offer assignment" };
export default function NewAssignmentPage() {
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Offer assignment"
        eyebrow="Select an approved campaign, driver, owned car and artwork"
      />
      <AssignmentForm />
    </div>
  );
}
