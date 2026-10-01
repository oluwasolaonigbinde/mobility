import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { CompanyProfileForm } from "./company-profile-form";

const company = {
  name: "Demo Advertiser Ltd",
  billing_email: "billing@example.com",
  address_country_code: "NG",
} as Parameters<typeof CompanyProfileForm>[0]["company"];

const LABELS = [
  "Legal or trading name",
  "Industry",
  "Billing email",
  "Billing contact",
  "Billing phone",
  "Operations contact",
  "Operations email",
  "Operations phone",
  "Address line 1",
  "Address line 2",
  "City",
  "State / region",
  "Postal code",
  "Country code",
];

it("renders every contact field with the saved values and a save action", () => {
  render(<CompanyProfileForm company={company} action={vi.fn()} />);
  expect(screen.getAllByRole("textbox").map((input) => input.getAttribute("name"))).toEqual([
    "name",
    "industry",
    "billing_email",
    "billing_contact_name",
    "billing_contact_phone",
    "operational_contact_name",
    "operational_contact_email",
    "operational_contact_phone",
    "address_line_1",
    "address_line_2",
    "address_city",
    "address_region",
    "address_postal_code",
    "address_country_code",
  ]);
  for (const label of LABELS) expect(screen.getByLabelText(label)).toBeEnabled();
  expect(screen.getByLabelText("Legal or trading name")).toHaveValue("Demo Advertiser Ltd");
  expect(screen.getByLabelText("Billing email")).toHaveValue("billing@example.com");
  expect(screen.getByLabelText("Industry")).toHaveValue("");
  expect(screen.getByLabelText("Country code")).toHaveAttribute("maxlength", "2");
  expect(screen.getByRole("button", { name: "Save company profile" })).toBeInTheDocument();
});

it("disables every field and hides the save action when read-only", () => {
  render(<CompanyProfileForm company={company} action={vi.fn()} readOnly />);
  for (const label of LABELS) expect(screen.getByLabelText(label)).toBeDisabled();
  expect(screen.queryByRole("button", { name: "Save company profile" })).not.toBeInTheDocument();
});
