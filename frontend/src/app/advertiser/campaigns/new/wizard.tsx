"use client";

import { useRef, useState, useTransition } from "react";
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
import { formatMoney } from "@/lib/format";
import {
  uploadCreativeFile,
  CREATIVE_UPLOAD_PHASE_LABELS,
  type CreativeUploadPhase,
} from "@/lib/files/creative-upload";
import { ZonesEditor } from "../[campaignId]/zones/zones-editor";
import type { components } from "@/lib/api/schema";

const STEPS = ["Basics", "Areas", "Your advert design", "Review"] as const;

const CREATIVE_TYPES = [
  { value: "image", label: "Image" },
  { value: "pdf", label: "PDF" },
] as const;

const PLACEMENTS = [
  { value: "vehicle_exterior", label: "Vehicle exterior" },
  { value: "vehicle_interior", label: "Vehicle interior" },
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
  2: ["creatives"],
};

export function CampaignWizard({
  currency,
  existingCampaign,
  campaignRequestId: initialCampaignRequestId,
  initialZones = [],
}: {
  currency: string;
  existingCampaign?: { id: string; name: string; basics?: CampaignWizardInput["basics"] };
  campaignRequestId?: string;
  initialZones?: components["schemas"]["CampaignZoneRead"][];
}) {
  const [campaignId, setCampaignId] = useState(existingCampaign?.id);
  const [step, setStep] = useState(existingCampaign ? 1 : 0);
  const [result, setResult] = useState<CreateCampaignState>({});
  const draftBasics = useRef<CampaignWizardInput["basics"] | null>(null);
  const draftSending = useRef(false);
  const [basicsLocked, setBasicsLocked] = useState(Boolean(existingCampaign));
  const [campaignRequestId, setCampaignRequestId] = useState(
    initialCampaignRequestId ?? crypto.randomUUID(),
  );
  const [uploadState, setUploadState] = useState<
    Record<string, { phase?: CreativeUploadPhase; error?: string }>
  >({});
  const uploadRequests = useRef<Record<string, { fingerprint: string; id: string }>>({});
  const [submitting, startTransition] = useTransition();

  const form = useForm<CampaignWizardInput, unknown, CampaignWizardOutput>({
    resolver: zodResolver(campaignWizardSchema),
    mode: "onTouched",
    defaultValues: {
      basics: {
        name: existingCampaign?.name ?? "",
        description: "",
        start_at: "",
        end_at: "",
        budget_amount: "",
        daily_budget_amount: "",
        ...existingCampaign?.basics,
      },
      creatives: [],
    },
  });

  const creatives = useFieldArray({ control: form.control, name: "creatives" });
  const { errors } = form.formState;

  async function next() {
    const fields = stepFields[step];
    const valid = fields ? await form.trigger(fields) : true;
    if (!valid || draftSending.current) return;
    if (step === 0 && !campaignId) {
      draftBasics.current ??= { ...form.getValues().basics };
      setBasicsLocked(true);
      window.history.replaceState(
        null,
        "",
        `/advertiser/campaigns/new?requestId=${campaignRequestId}`,
      );
      draftSending.current = true;
      setResult({});
      startTransition(async () => {
        try {
          const state = await createCampaignAction(
            { basics: draftBasics.current!, creatives: [] },
            undefined,
            campaignRequestId,
            true,
          );
          setResult(state);
          if (state.createdCampaignId && !state.error) {
            setCampaignId(state.createdCampaignId);
            window.history.replaceState(
              null,
              "",
              `/advertiser/campaigns/new?campaignId=${state.createdCampaignId}`,
            );
            setStep(1);
          }
        } catch {
          setResult({
            error: "Your draft couldn't be confirmed. Try again to check the same saved details.",
          });
        } finally {
          draftSending.current = false;
        }
      });
    } else setStep((s) => Math.min(s + 1, STEPS.length - 1));
  }

  async function uploadCreative(index: number, fieldId: string, file: File | undefined) {
    if (!file) return;
    form.setValue(`creatives.${index}.stored_file_id`, "", { shouldValidate: true });
    form.setValue(`creatives.${index}.original_filename`, file.name);
    const fingerprint = `${file.name}:${file.type}:${file.size}:${file.lastModified}`;
    if (uploadRequests.current[fieldId]?.fingerprint !== fingerprint) {
      uploadRequests.current[fieldId] = { fingerprint, id: crypto.randomUUID() };
    }
    setUploadState((current) => ({ ...current, [fieldId]: { phase: "hashing" } }));
    try {
      const uploaded = await uploadCreativeFile(
        file,
        (phase) => setUploadState((current) => ({ ...current, [fieldId]: { phase } })),
        { clientRequestId: uploadRequests.current[fieldId]?.id },
      );
      form.setValue(`creatives.${index}.stored_file_id`, uploaded.storedFileId, {
        shouldDirty: true,
        shouldValidate: true,
      });
      form.setValue(`creatives.${index}.creative_type`, uploaded.creativeType, {
        shouldDirty: true,
      });
    } catch (error) {
      setUploadState((current) => ({
        ...current,
        [fieldId]: {
          error: error instanceof Error ? error.message : "The upload failed. Retry the file.",
        },
      }));
    }
  }

  function submit() {
    // handleSubmit has already validated via the resolver; send the RAW
    // input values — the server action re-parses them authoritatively
    // (the schema's transforms are not idempotent).
    const raw = form.getValues();
    setResult({});
    startTransition(async () => {
      const state = await createCampaignAction(raw, campaignId, campaignRequestId);
      if (state.campaignRequestId) {
        setCampaignRequestId(state.campaignRequestId);
        window.history.replaceState(
          null,
          "",
          `/advertiser/campaigns/new?requestId=${state.campaignRequestId}`,
        );
      }
      if (state.createdCampaignId) {
        setCampaignId(state.createdCampaignId);
        window.history.replaceState(
          null,
          "",
          `/advertiser/campaigns/new?campaignId=${state.createdCampaignId}`,
        );
      }
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
    <div className="pb-12">
      {/* Stepper */}
      <ol className="mb-6 flex flex-wrap items-center gap-2" aria-label="Progress">
        {STEPS.map((label, i) =>
          campaignId && i === 0 ? null : (
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
          ),
        )}
      </ol>

      {result.error ? (
        <p role="alert" className="text-coral mb-4 text-sm">
          {result.error}
        </p>
      ) : null}
      <Panel className="p-6 md:p-8">
        {step === 0 ? (
          <fieldset disabled={basicsLocked} className="flex max-w-xl flex-col gap-5">
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
                  Starts, Nigeria time (WAT)
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
                  Ends, Nigeria time (WAT)
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
                  Daily budget ({currency})
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
              <p className="font-medium">Saved as a draft</p>
              <p className="text-muted mt-1">
                Continue saves your draft, then you can choose its areas and advert design. Nothing
                is sent for review or payment yet.
              </p>
              <p className="text-muted mt-1">
                To submit for review, the campaign needs start and end dates, a total budget and at
                least one target area. You can save a draft without them.
              </p>
            </div>
          </fieldset>
        ) : null}

        {step === 1 && campaignId ? (
          <div>
            <p className="text-muted mb-4 text-sm">
              Your draft is saved. Draw and name the areas where you’d like your advert seen. You
              can add or change areas later.
            </p>
            <ZonesEditor key={campaignId} campaignId={campaignId} zones={initialZones} />
          </div>
        ) : null}
        {step === 2 ? (
          <div className="flex flex-col gap-5">
            <p className="text-muted text-sm">
              Upload your advert design. We’ll check the file before adding it to your draft.
            </p>

            {creatives.fields.map((field, i) => (
              <Panel key={field.id} className="bg-raised/60 relative p-5">
                <button
                  type="button"
                  aria-label={`Remove design ${i + 1}`}
                  onClick={() => creatives.remove(i)}
                  disabled={Boolean(
                    uploadState[field.id]?.phase && uploadState[field.id]?.phase !== "clean",
                  )}
                  className="micro text-faint hover:text-coral absolute top-4 right-4 transition-colors"
                >
                  Remove
                </button>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="sm:col-span-2">
                    <label htmlFor={`cr-name-${i}`} className={labelClass}>
                      Design name *
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
                    <label htmlFor={`cr-file-${i}`} className={labelClass}>
                      Design file *
                    </label>
                    <input
                      id={`cr-file-${i}`}
                      type="file"
                      accept="image/png,image/jpeg,image/webp,application/pdf"
                      disabled={Boolean(
                        uploadState[field.id]?.phase && uploadState[field.id]?.phase !== "clean",
                      )}
                      className={cx(inputClass, "mt-1.5 font-mono text-xs")}
                      onChange={(event) =>
                        void uploadCreative(i, field.id, event.currentTarget.files?.[0])
                      }
                    />
                    <input type="hidden" {...form.register(`creatives.${i}.stored_file_id`)} />
                    <input type="hidden" {...form.register(`creatives.${i}.original_filename`)} />
                    {uploadState[field.id]?.phase ? (
                      <p className="text-muted mt-1 text-xs" aria-live="polite">
                        {CREATIVE_UPLOAD_PHASE_LABELS[uploadState[field.id]!.phase!]}
                      </p>
                    ) : null}
                    {uploadState[field.id]?.error ? (
                      <p className={errorClass} role="alert">
                        {uploadState[field.id]?.error} Select the file again to retry.
                      </p>
                    ) : errors.creatives?.[i]?.stored_file_id ? (
                      <p className={errorClass}>{errors.creatives[i]?.stored_file_id?.message}</p>
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
                  stored_file_id: "",
                  original_filename: "",
                })
              }
              className="border-edge text-muted hover:border-edge-strong hover:text-ink rounded-lg border border-dashed px-4 py-3.5 text-sm transition-colors"
            >
              + Add advert design
            </button>
            <p className="micro text-faint">
              You can also add your design later from the campaign page.
            </p>
          </div>
        ) : null}

        {step === 3 ? (
          <div className="flex max-w-xl flex-col gap-4">
            <h2 className="font-display text-xl font-semibold">Review your draft</h2>
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
                    ? formatMoney(values.basics.budget_amount, currency)
                    : "not set",
                ],
                [
                  "Daily budget",
                  values.basics.daily_budget_amount
                    ? formatMoney(values.basics.daily_budget_amount, currency)
                    : "not set",
                ],
                [
                  campaignId ? "Campaign" : "Create as",
                  campaignId ? "Existing campaign — details unchanged" : "Draft",
                ],
                [
                  "Advert design",
                  values.creatives.length ? `${values.creatives.length} ready to add` : "Add later",
                ],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-6 py-2.5">
                  <dt className="micro text-faint">{k}</dt>
                  <dd className="text-right">{v}</dd>
                </div>
              ))}
            </dl>
            {result.error && result.createdCampaignId ? (
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
        {step > (campaignId ? 1 : 0) ? (
          <Button type="button" variant="ghost" onClick={() => setStep((s) => s - 1)}>
            ← Back
          </Button>
        ) : (
          <Link href="/advertiser/campaigns" className="micro text-muted hover:text-ink">
            My campaigns
          </Link>
        )}
        {step < STEPS.length - 1 ? (
          <Button
            type="button"
            disabled={submitting}
            onClick={(event) => {
              event.preventDefault();
              void next();
            }}
          >
            {submitting ? "Saving…" : "Continue →"}
          </Button>
        ) : (
          <Button type="button" onClick={form.handleSubmit(submit)} disabled={submitting}>
            {submitting ? "Saving…" : "Finish draft"}
          </Button>
        )}
      </div>
    </div>
  );
}
