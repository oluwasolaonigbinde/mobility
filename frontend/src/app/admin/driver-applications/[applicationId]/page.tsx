import Link from "next/link";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { PageHeader } from "@/components/ui/page-header";
import { PersonPayeeDecisionActions } from "../person-payee-decision-actions";
import { VehicleDecisionActions } from "../vehicle-decision-actions";
import { QueueUnavailable } from "../../queue-search";

export default async function ApplicationReview({
  params,
}: {
  params: Promise<{ applicationId: string }>;
}) {
  const { applicationId } = await params;
  const { data: a } = await createApiClient(await getSessionToken()).GET(
    "/api/v1/admin/driver-applications/{application_id}",
    { params: { path: { application_id: applicationId } } },
  );
  if (!a) return <QueueUnavailable />;
  const person = a.person_payee;
  const vehicle = a.vehicle;
  return (
    <div className="mx-auto max-w-4xl">
      <Link href="/admin/driver-applications" className="text-cyan text-sm">
        ← All applications
      </Link>
      <PageHeader title={a.full_name} eyebrow={`${a.email} · ${a.status.replaceAll("_", " ")}`} />
      <p className="text-muted mb-5 text-sm">
        Review the current evidence below. Sensitive information is purpose-audited and hidden
        automatically after one minute.
      </p>
      <div className="grid gap-6 md:grid-cols-2">
        <section className="border-edge min-w-0 rounded-xl border p-4">
          <h2 className="mb-3 font-medium">Person and payee</h2>
          <p className="text-muted mb-3 text-sm">
            {person?.status.replaceAll("_", " ") ?? "Not submitted"}{" "}
            {person?.version ? `· Version ${person.version}` : ""}
          </p>
          {person?.status === "pending_review" &&
          person.submission_id &&
          person.bank_account_version_id ? (
            <PersonPayeeDecisionActions
              key={person.submission_id}
              applicationId={a.id}
              submissionId={person.submission_id}
              bankAccountVersionId={person.bank_account_version_id}
              bankAccountVerified={person.bank_account_verified}
              documentFileIds={person.document_file_ids ?? {}}
            />
          ) : (
            <p>No current person/payee decision is awaiting review.</p>
          )}
        </section>
        <section className="border-edge min-w-0 rounded-xl border p-4">
          <h2 className="mb-3 font-medium">Vehicle · {vehicle?.plate_number ?? "Not supplied"}</h2>
          <p className="text-muted mb-3 text-sm">
            {vehicle?.status.replaceAll("_", " ") ?? "Not submitted"}
          </p>
          {vehicle?.vehicle_id &&
          vehicle.submission_id &&
          ["approved", "pending_review"].includes(vehicle.status) ? (
            <VehicleDecisionActions
              key={vehicle.submission_id}
              applicationId={a.id}
              vehicleId={vehicle.vehicle_id}
              submissionId={vehicle.submission_id}
              documentFileIds={vehicle.document_file_ids ?? {}}
              status={vehicle.status}
            />
          ) : (
            <p>No current vehicle decision is awaiting review.</p>
          )}
        </section>
      </div>
    </div>
  );
}
