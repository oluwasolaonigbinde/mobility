import { expect, it } from "vitest";
import { companyProfileUpdate } from "./company-profile";

it("trims every field and sends blank optional fields as null", () => {
  const data = new FormData();
  data.set("name", "  Demo Advertiser Ltd  ");
  data.set("billing_email", " billing@example.com ");
  data.set("industry", "   ");
  data.set("address_country_code", "ng");

  expect(companyProfileUpdate(data)).toEqual({
    name: "Demo Advertiser Ltd",
    billing_email: "billing@example.com",
    billing_contact_name: null,
    billing_contact_phone: null,
    operational_contact_name: null,
    operational_contact_email: null,
    operational_contact_phone: null,
    address_line_1: null,
    address_line_2: null,
    address_city: null,
    address_region: null,
    address_postal_code: null,
    address_country_code: "ng",
    industry: null,
  });
});

it("sends an empty name rather than null so the server rejects it", () => {
  expect(companyProfileUpdate(new FormData()).name).toBe("");
});
