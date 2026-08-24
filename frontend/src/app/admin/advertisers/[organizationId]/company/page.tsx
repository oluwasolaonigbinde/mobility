import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import { updateCompanyAction } from "./actions";

export const metadata: Metadata = { title: "Advertiser company" };

export default async function AdminCompanyPage({
  params,
  searchParams,
}: {
  params: Promise<{ organizationId: string }>;
  searchParams: Promise<{ campaign?: string; saved?: string; error?: string }>;
}) {
  const { organizationId } = await params;
  const notice = await searchParams;
  const api = createApiClient(await getSessionToken());
  let company;
  try {
    ({ data: company } = await api.GET(
      "/api/v1/admin/advertiser-organizations/{organization_id}/company",
      { params: { path: { organization_id: organizationId } } },
    ));
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  if (!company) notFound();

  return (
    <div className="animate-rise mx-auto max-w-5xl">
      {notice.campaign ? (
        <nav className="micro text-muted mb-4">
          <Link href={`/admin/billing/${notice.campaign}`}>Campaign billing</Link> / Company
        </nav>
      ) : null}
      <PageHeader title={company.name} eyebrow="Advertiser billing and operational contacts" />
      {notice.saved ? <p className="text-green mb-4 text-sm">Company profile saved.</p> : null}
      {notice.error ? <p className="text-coral mb-4 text-sm">{notice.error}</p> : null}
      <Panel className="p-6">
        <form
          action={updateCompanyAction.bind(null, organizationId, notice.campaign)}
          className="grid gap-5 md:grid-cols-2"
        >
          <Field name="name" label="Legal or trading name" defaultValue={company.name} required />
          <Field name="industry" label="Industry" defaultValue={company.industry ?? ""} />
          <Field
            name="billing_email"
            label="Billing email"
            type="email"
            defaultValue={company.billing_email ?? ""}
          />
          <Field
            name="billing_contact_name"
            label="Billing contact"
            defaultValue={company.billing_contact_name ?? ""}
          />
          <Field
            name="billing_contact_phone"
            label="Billing phone"
            defaultValue={company.billing_contact_phone ?? ""}
          />
          <Field
            name="operational_contact_name"
            label="Operations contact"
            defaultValue={company.operational_contact_name ?? ""}
          />
          <Field
            name="operational_contact_email"
            label="Operations email"
            type="email"
            defaultValue={company.operational_contact_email ?? ""}
          />
          <Field
            name="operational_contact_phone"
            label="Operations phone"
            defaultValue={company.operational_contact_phone ?? ""}
          />
          <Field
            name="address_line_1"
            label="Address line 1"
            defaultValue={company.address_line_1 ?? ""}
          />
          <Field
            name="address_line_2"
            label="Address line 2"
            defaultValue={company.address_line_2 ?? ""}
          />
          <Field name="address_city" label="City" defaultValue={company.address_city ?? ""} />
          <Field
            name="address_region"
            label="State / region"
            defaultValue={company.address_region ?? ""}
          />
          <Field
            name="address_postal_code"
            label="Postal code"
            defaultValue={company.address_postal_code ?? ""}
          />
          <Field
            name="address_country_code"
            label="Country code"
            maxLength={2}
            defaultValue={company.address_country_code ?? ""}
          />
          <div className="md:col-span-2">
            <Button type="submit">Save company profile</Button>
          </div>
        </form>
      </Panel>
    </div>
  );
}
