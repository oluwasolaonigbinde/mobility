import type { components } from "@/lib/api/schema";

export type CompanyProfile = components["schemas"]["CompanyProfileRead"];
type CompanyProfileUpdate = components["schemas"]["CompanyProfileUpdate"];

/** The PATCH body both company forms send: trimmed name, blank optional fields as null. */
export function companyProfileUpdate(formData: FormData): CompanyProfileUpdate {
  const optional = (name: string) => String(formData.get(name) ?? "").trim() || null;
  return {
    name: String(formData.get("name") ?? "").trim(),
    billing_email: optional("billing_email"),
    billing_contact_name: optional("billing_contact_name"),
    billing_contact_phone: optional("billing_contact_phone"),
    operational_contact_name: optional("operational_contact_name"),
    operational_contact_email: optional("operational_contact_email"),
    operational_contact_phone: optional("operational_contact_phone"),
    address_line_1: optional("address_line_1"),
    address_line_2: optional("address_line_2"),
    address_city: optional("address_city"),
    address_region: optional("address_region"),
    address_postal_code: optional("address_postal_code"),
    address_country_code: optional("address_country_code"),
    industry: optional("industry"),
  };
}
