"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { useForm, useFieldArray, type FieldPath } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  campaignWizardSchema,
  type CampaignWizard as CampaignWizardOutput,
  type CampaignWizardInput,
} from "@/lib/campaigns/schema";
import { createCampaignAction, type CreateCampaignState } from "./actions";
import { Panel } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { cx } from "@/lib/cx";

const STEPS = ["Basics", "Creatives", "Review"] as const;

const CREATIVE_TYPES = [
  { value: "image", label: "Image" },
  { value: "video", label: "Video" },
  { value: "html", label: "HTML" },
  { value: "text", label: "Text" },
  { value: "other", label: "Other" },
] as const;

const PLACEMENTS = [
  { value: "vehicle_exterior", label: "Vehicle exterior" },
  { value: "vehicle_interior", label: "Vehicle interior" },
  { value: "digital_screen", label: "Digital screen" },
  { value: "print", label: "Print" },
  { value: "other", label: "Other" },
] as const;

/** Fields validated before leaving each step. */
const stepFields: Record<number, FieldPath<CampaignWizardInput>[]> = {
  0: [
    "basics.name",
    "basics.description",
    "basics.start_at",
    "basics.end_at",
    "basics.budget_amount",
    "basics.daily_budget_amount",
  ],
  1: ["creatives"],
};

export function CampaignWizard({ currency }: { currency: string }) {
  const [step, setStep] = useState(0);
  const [result, setResult] = useState<CreateCampaignState>({});
  const [submitting, startTransition] = useTransition();

  const form = useForm<CampaignWizardInput, unknown, CampaignWizardOutput>({
    resolver: zodResolver(campaignWizardSchema),
    mode: "onTouched",
    defaultValues: {
      basics: {
        name: "",
        description: "",
        start_at: "",
        end_at: "",
        budget_amount: "",
        daily_budget_amount: "",
      },
      creatives: [],
    },
  });

  const creatives = useFieldArray({ control: form.control, name: "creatives" });
  const { errors } = form.formState;

  async function next() {
    const fields = stepFields[step];
    const valid = fields ? await form.trigger(fields) : true;
    if (valid) setStep((s) => Math.min(s + 1, STEPS.length - 1));
  }

  function submit() {
    // handleSubmit has already validated via the resolver; send the RAW
    // input values — the server action re-parses them authoritatively
    // (the schema's transforms are not idempotent).
    const raw = form.getValues();
    setResult({});
    startTransition(async () => {
      const state = await createCampaignAction(raw);
      // On success the action redirects; reaching here means failure.
      setResult(state);
    });
  }

  const values = form.watch();

  const inputClass =
    "h-11 w-full rounded-lg border border-edge bg-raised px-3.5 text-sm text-ink placeholder:text-faint transition-colors focus:border-amber focus:outline-none";
  const labelClass = "micro text-muted";
  const errorClass = "mt-1 text-xs text-coral";

  return (
    // pb-24 keeps the footer's Continue/Back clear of the floating theme
    // pill (fixed bottom-right) when the page is scrolled to its end.
    <form onSubmit={form.handleSubmit(submit)} noValidate className="pb-24">
      {/* Stepper */}
      <ol className="mb-6 flex items-center gap-2" aria-label="Progress">
        {STEPS.map((label, i) => (
          <li key={label} className="flex items-center gap-2">
            <span
              aria-current={i === step ? "step" : undefined}
              className={cx(
                "micro flex items-center gap-2 rounded-full border px-3 py-1.5",
                i === step
                  ? "border-amber/50 bg-amber/10 text-amber"
                  : i < step
                    ? "border-green/40 bg-green/10 text-green"
                    : "border-edge text-faint",
              )}
            >
              {i < step ? "✓" : i + 1} {label}
            </span>
            {i < STEPS.length - 1 ? <span className="text-faint">—</span> : null}
          </li>
        ))}
      </ol>

      <Panel className="p-6 md:p-8">
        {step === 0 ? (
          <div className="flex max-w-xl flex-col gap-5">
            <div>
              <label htmlFor="c-name" className={labelClass}>
                Campaign name *
              </label>
              <input
                id="c-name"
                className={cx(inputClass, "mt-1.5")}
                placeholder="e.g. Yello Season Q3"
                {...form.register("basics.name")}
              />
              {errors.basics?.name ? (
                <p className={errorClass}>{errors.basics.name.message}</p>
              ) : null}
            </div>

            <div>
              <label htmlFor="c-desc" className={labelClass}>
                Description
              </label>
              <textarea
                id="c-desc"
                rows={3}
                className={cx(inputClass, "mt-1.5 h-auto py-2.5")}
                placeholder="What is this campaign about?"
                {...form.register("basics.description")}
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="c-start" className={labelClass}>
                  Starts
                </label>
                <input
                  id="c-start"
                  type="datetime-local"
                  className={cx(inputClass, "mt-1.5")}
                  {...form.register("basics.start_at")}
                />
                {errors.basics?.start_at ? (
                  <p className={errorClass}>{errors.basics.start_at.message}</p>
                ) : null}
              </div>
              <div>
                <label htmlFor="c-end" className={labelClass}>
                  Ends
                </label>
                <input
                  id="c-end"
                  type="datetime-local"
                  className={cx(inputClass, "mt-1.5")}
                  {...form.register("basics.end_at")}
                />
                {errors.basics?.end_at ? (
                  <p className={errorClass}>{errors.basics.end_at.message}</p>
                ) : null}
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="c-budget" className={labelClass}>
                  Total budget ({currency})
                </label>
                <input
                  id="c-budget"
                  inputMode="decimal"
                  className={cx(inputClass, "mt-1.5 font-mono")}
                  placeholder="e.g. 5000000"
                  {...form.register("basics.budget_amount")}
                />
                {errors.basics?.budget_amount ? (
                  <p className={errorClass}>{errors.basics.budget_amount.message}</p>
                ) : null}
              </div>
              <div>
                <label htmlFor="c-daily" className={labelClass}>
                  Daily cap ({currency})
                </label>
                <input
                  id="c-daily"
                  inputMode="decimal"
                  className={cx(inputClass, "mt-1.5 font-mono")}
                  placeholder="optional"
                  {...form.register("basics.daily_budget_amount")}
                />
                {errors.basics?.daily_budget_amount ? (
                  <p className={errorClass}>{errors.basics.daily_budget_amount.message}</p>
                ) : null}
              </div>
            </div>

            <div className="border-amber/30 bg-amber/10 rounded-lg border p-3.5 text-sm">
              <p className="font-medium">Created as a draft</p>
              <p className="text-muted mt-1">
                Submit the completed campaign for admin review from its detail page. Scheduling and
                activation are not available here.
              </p>
            </div>
          </div>
        ) : null}

        {step === 1 ? (
          <div className="flex flex-col gap-5">
            <p className="text-muted text-sm">
              Register the creative assets this campaign will run. Files are referenced by URL for
              now — the asset itself stays wherever it&apos;s hosted.
            </p>

            {creatives.fields.map((field, i) => (
              <Panel key={field.id} className="bg-raised/60 relative p-5">
                <button
                  type="button"
                  aria-label={`Remove creative ${i + 1}`}
                  onClick={() => creatives.remove(i)}
                  className="micro text-faint hover:text-coral absolute top-4 right-4 transition-colors"
                >
                  Remove
                </button>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="sm:col-span-2">
                    <label htmlFor={`cr-name-${i}`} className={labelClass}>
                      Creative name *
                    </label>
                    <input
                      id={`cr-name-${i}`}
                      className={cx(inputClass, "mt-1.5")}
                      placeholder="e.g. Full wrap — amber"
                      {...form.register(`creatives.${i}.name`)}
                    />
                    {errors.creatives?.[i]?.name ? (
                      <p className={errorClass}>{errors.creatives[i]?.name?.message}</p>
                    ) : null}
                  </div>
                  <div>
                    <label htmlFor={`cr-type-${i}`} className={labelClass}>
                      Type
                    </label>
                    <select
                      id={`cr-type-${i}`}
                      className={cx(inputClass, "mt-1.5")}
                      {...form.register(`creatives.${i}.creative_type`)}
                    >
                      {CREATIVE_TYPES.map((t) => (
                        <option key={t.value} value={t.value}>
                          {t.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor={`cr-place-${i}`} className={labelClass}>
                      Placement
                    </label>
                    <select
                      id={`cr-place-${i}`}
                      className={cx(inputClass, "mt-1.5")}
                      {...form.register(`creatives.${i}.placement`)}
                    >
                      {PLACEMENTS.map((p) => (
                        <option key={p.value} value={p.value}>
                          {p.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="sm:col-span-2">
                    <label htmlFor={`cr-url-${i}`} className={labelClass}>
                      Asset URL
                    </label>
                    <input
                      id={`cr-url-${i}`}
                      type="url"
                      className={cx(inputClass, "mt-1.5 font-mono text-xs")}
                      placeholder="https://cdn.example.com/wrap-v2.png"
                      {...form.register(`creatives.${i}.asset_url`)}
                    />
                    {errors.creatives?.[i]?.asset_url ? (
                      <p className={errorClass}>{errors.creatives[i]?.asset_url?.message}</p>
                    ) : null}
                  </div>
                </div>
              </Panel>
            ))}

            <button
              type="button"
              onClick={() =>
                creatives.append({
                  name: "",
                  creative_type: "image",
                  placement: "vehicle_exterior",
                  asset_url: "",
                })
              }
              className="border-edge text-muted hover:border-edge-strong hover:text-ink rounded-lg border border-dashed px-4 py-3.5 text-sm transition-colors"
            >
              + Add creative
            </button>
            <p className="micro text-faint">
              Optional — you can create the campaign without creatives and add them later.
            </p>
          </div>
        ) : null}

        {step === 2 ? (
          <div className="flex max-w-xl flex-col gap-4">
            <h2 className="font-display text-xl font-semibold">Review &amp; create</h2>
            <dl className="divide-edge/60 divide-y text-sm">
              {[
                ["Name", values.basics.name || "—"],
                ["Description", values.basics.description || "—"],
                [
                  "Window",
                  `${values.basics.start_at || "not set"} → ${values.basics.end_at || "not set"}`,
                ],
                [
                  "Budget",
                  values.basics.budget_amount
                    ? `${currency} ${values.basics.budget_amount}`
                    : "not set",
                ],
                [
                  "Daily cap",
                  values.basics.daily_budget_amount
                    ? `${currency} ${values.basics.daily_budget_amount}`
                    : "not set",
                ],
                ["Create as", "Draft"],
                [
                  "Creatives",
                  values.creatives.length ? `${values.creatives.length} attached` : "none",
                ],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-6 py-2.5">
                  <dt className="micro text-faint">{k}</dt>
                  <dd className="text-right">{v}</dd>
                </div>
              ))}
            </dl>
            {result.error ? (
              <div
                role="alert"
                className="border-coral/40 bg-coral/10 text-coral rounded-lg border px-4 py-3 text-sm"
              >
                {result.error}
                {result.createdCampaignId ? (
                  <>
                    {" "}
                    <Link
                      href={`/advertiser/campaigns/${result.createdCampaignId}`}
                      className="underline"
                    >
                      Open the created campaign
                    </Link>
                  </>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}
      </Panel>

      {/* Footer nav */}
      <div className="mt-5 flex items-center justify-between">
        {step > 0 ? (
          <Button type="button" variant="ghost" onClick={() => setStep((s) => s - 1)}>
            ← Back
          </Button>
        ) : (
          <Link href="/advertiser/campaigns" className="micro text-muted hover:text-ink">
            Cancel
          </Link>
        )}
        {step < STEPS.length - 1 ? (
          <Button type="button" onClick={next}>
            Continue →
          </Button>
        ) : (
          <Button type="submit" disabled={submitting}>
            {submitting ? "Creating…" : "Create campaign"}
          </Button>
        )}
      </div>
    </form>
  );
}
