"use client";

import { useActionState } from "react";
import {
  submitCampaignEnquiry,
  type CampaignEnquiryState,
  type EnquiryField,
} from "@/app/campaign-enquiry-actions";
import { CONTACT } from "@/lib/marketing/site";

// OWNER — REQ-070: enquire on-site; Terrax still provisions advertiser accounts.
const fields: {
  name: EnquiryField;
  label: string;
  max: number;
  type?: string;
  optional?: boolean;
}[] = [
  { name: "company", label: "Company", max: 160, type: "text" },
  { name: "contact_name", label: "Contact name", max: 160, type: "text" },
  { name: "email", label: "Email address", max: 254, type: "email" },
  { name: "phone", label: "Phone number (optional)", max: 32, type: "tel", optional: true },
  { name: "brief", label: "Tell us about your campaign", max: 2000 },
];

export function CampaignEnquiry() {
  const [state, action, pending] = useActionState<CampaignEnquiryState, FormData>(
    submitCampaignEnquiry,
    {},
  );
  return (
    <section id="campaign-enquiry" aria-labelledby="campaign-enquiry-title">
      <div className="mx-auto max-w-3xl px-5 py-16 md:px-8">
        <h2 id="campaign-enquiry-title" className="font-terrax-display text-3xl font-extrabold">
          Request a campaign quote
        </h2>
        <p className="text-terrax-ink-soft mt-4">
          Tell Terrax Media what you have in mind, including your target areas and preferred dates.
          Our team will discuss your campaign and prepare a quotation.
        </p>
        {state.submitted ? (
          <p role="status" className="border-terrax-green mt-6 rounded-xl border p-5">
            Your enquiry has been sent to Terrax Media. Our team will reply using the contact
            details you provided.
          </p>
        ) : (
          <form action={action} aria-busy={pending} className="mt-8 space-y-5">
            {fields.map((field) => {
              const id = `enquiry-${field.name}`;
              const error = state.fieldErrors?.[field.name];
              const props = {
                id,
                name: field.name,
                required: !field.optional,
                maxLength: field.max,
                defaultValue: state.values?.[field.name] ?? "",
                "aria-invalid": error ? true : undefined,
                "aria-describedby": error ? `${id}-error` : undefined,
                className:
                  "border-terrax-ink/25 bg-terrax-card mt-2 block w-full rounded-lg border px-4 py-3",
              };
              return (
                <div key={field.name}>
                  <label htmlFor={id} className="text-sm font-semibold">
                    {field.label}
                  </label>
                  {field.type ? (
                    <input {...props} type={field.type} />
                  ) : (
                    <textarea {...props} rows={5} />
                  )}
                  {error ? (
                    <p
                      id={`${id}-error`}
                      role="alert"
                      className="text-terrax-crimson-ink mt-1 text-sm"
                    >
                      {error}
                    </p>
                  ) : null}
                </div>
              );
            })}
            <p className="text-terrax-ink-soft text-sm">
              Terrax Media uses these details to respond to your enquiry. This does not create an
              account or launch a campaign. Please do not include identity documents or bank
              details.
            </p>
            {state.error ? (
              <p role="alert" className="text-terrax-crimson-ink">
                {state.error}
              </p>
            ) : null}
            <button
              disabled={pending}
              className="bg-terrax-ink text-terrax-card rounded-full px-6 py-3 font-semibold disabled:opacity-60"
            >
              {pending ? "Sending enquiry…" : "Send enquiry"}
            </button>
            {pending ? <p role="status">Sending your enquiry…</p> : null}
          </form>
        )}
        <p className="text-terrax-ink-soft mt-6 text-sm break-words">
          Prefer email?{" "}
          <a className="underline underline-offset-4" href={`mailto:${CONTACT.email}`}>
            {CONTACT.email}
          </a>
        </p>
      </div>
    </section>
  );
}
