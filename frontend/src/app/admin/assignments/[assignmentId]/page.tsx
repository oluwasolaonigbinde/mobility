import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { PageHeader } from "@/components/ui/page-header";
import { ActivateAssignmentButton } from "../activate-button";
import { QueueUnavailable } from "../../queue-search";

export default async function AssignmentReadiness({
  params,
}: {
  params: Promise<{ assignmentId: string }>;
}) {
  const { assignmentId } = await params;
  const { data } = await createApiClient(await getSessionToken()).GET(
    "/api/v1/admin/campaign-assignments/{assignment_id}/readiness",
    { params: { path: { assignment_id: assignmentId } } },
  );
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="Activation readiness" eyebrow="Administrator preparation" />
      <p className="text-muted mb-5">
        Checking readiness does not activate work, reserve funding or record a decision. Every
        prerequisite is checked again when you activate.
      </p>
      {!data ? (
        <QueueUnavailable />
      ) : (
        <section className="border-edge rounded-xl border p-5">
          <h2 className="font-medium">
            {data.ready
              ? "Ready for final activation"
              : data.blocker_code === "ASSIGNMENT_ALREADY_ACTIVE"
                ? "Already active"
                : "Preparation required"}
          </h2>
          <p className="my-4">{data.message}</p>
          {data.ready ? (
            <ActivateAssignmentButton assignmentId={assignmentId} />
          ) : data.blocker_code === "ASSIGNMENT_ALREADY_ACTIVE" ? (
            <Link href="/admin/assignments" className="text-cyan">
              Back to assignments
            </Link>
          ) : (
            <div className="flex flex-wrap gap-4">
              <Link href="/admin/approvals" className="text-cyan">
                Review approvals and installation
              </Link>
              <Link href="/admin/billing" className="text-cyan">
                Review funding with finance
              </Link>
              <Link href="/admin/driver-applications" className="text-cyan">
                Review driver and vehicle eligibility
              </Link>
            </div>
          )}
        </section>
      )}
      <p className="text-muted mt-5">
        Physical installation/removal, permits and any provider work require their recorded
        operations evidence. This check does not confirm campaign closeout or cash settlement.
      </p>
    </div>
  );
}
