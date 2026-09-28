import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Panel } from "@/components/ui/panel";
import type { CompanyProfile } from "@/lib/advertiser/company-profile";

/** Company contact form shared by the advertiser and admin company pages. */
export function CompanyProfileForm({
  company,
  action,
  readOnly = false,
}: {
  company: CompanyProfile;
  action: (formData: FormData) => void | Promise<void>;
  readOnly?: boolean;
}) {
  return (
    <Panel className="p-6">
      <form action={action}>
        <fieldset disabled={readOnly} className="grid gap-5 md:grid-cols-2">
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
          {readOnly ? null : (
            <div className="md:col-span-2">
              <Button type="submit">Save company profile</Button>
            </div>
          )}
        </fieldset>
      </form>
    </Panel>
  );
}
