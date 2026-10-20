import Link from "next/link";
import { z } from "zod";
import { notFound, redirect } from "next/navigation";
import { createApiClient } from "@/lib/api/client";
import { readStaffEnquiry } from "@/lib/api/audit-batch2";
import { ApiError } from "@/lib/api/errors";
import { requireRole } from "@/lib/auth/current-user";
import { getSessionToken } from "@/lib/auth/session";
import { formatDateTime } from "@/lib/format";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { QueueUnavailable } from "../../queue-search";
import { ConvertEnquiryForm } from "./convert-form";

export const metadata = { title: "Advertising enquiry" };
export default async function EnquiryPage({ params }: { params: Promise<{ enquiryId: string }> }) {
  await requireRole("admin");
  const { enquiryId } = await params;
  if (!z.uuid().safeParse(enquiryId).success) notFound();
  let enquiry;
  try {
    enquiry = (await readStaffEnquiry(createApiClient(await getSessionToken()), enquiryId)).data;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/login");
    if (error instanceof ApiError && [403, 404].includes(error.status)) notFound();
  }
  if (!enquiry)
    return (
      <>
        <QueueUnavailable />
        <Link href={`/admin/enquiries/${enquiryId}`} className="text-green underline">
          Try again
        </Link>
      </>
    );
  if (enquiry.id !== enquiryId) notFound();
  if (!["new", "converted"].includes(enquiry.status)) return <QueueUnavailable />;
  return (
    <div className="mx-auto max-w-3xl">
      <Link href="/admin/enquiries" className="text-green mb-4 inline-block text-sm underline">
        Back to new enquiries
      </Link>
      <PageHeader
        title={enquiry.company}
        eyebrow={`Received ${formatDateTime(enquiry.created_at)} · Nigeria time (WAT)`}
      />
      <Panel className="p-6">
        <h2 className="font-medium">Contact</h2>
        <p className="mt-3">{enquiry.contact_name}</p>
        <p className="mt-1 break-all">{enquiry.email}</p>
        {enquiry.phone ? <p className="mt-1">{enquiry.phone}</p> : null}
        <h2 className="mt-6 font-medium">What they need</h2>
        <p className="mt-3 whitespace-pre-line">{enquiry.brief}</p>
        {enquiry.status === "converted" ? (
          enquiry.organization_id ? (
            <Link
              className="text-green mt-5 inline-block underline"
              href={`/admin/advertisers/${enquiry.organization_id}`}
            >
              View advertiser
            </Link>
          ) : (
            <QueueUnavailable />
          )
        ) : (
          <ConvertEnquiryForm enquiryId={enquiryId} />
        )}
      </Panel>
    </div>
  );
}
