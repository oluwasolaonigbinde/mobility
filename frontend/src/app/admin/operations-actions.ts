"use server";
import { revalidatePath } from "next/cache";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { ApiError } from "@/lib/api/errors";
import { z } from "zod";
export async function resolveOperation(_state: { error?: string; done?: string }, form: FormData) {
  const parsed = z
    .object({
      kind: z.enum(["contact", "apply", "discard"]),
      id: z.string().uuid(),
      trip: z.string().uuid().optional(),
      note: z.string().trim().min(1).max(2000),
      outcome: z.enum(["attempted", "reached", "failed"]),
      confirmed: z.literal(true),
    })
    .safeParse({
      kind: form.get("kind"),
      id: form.get("id"),
      trip: form.get("trip") || undefined,
      note: form.get("note"),
      outcome: form.get("outcome") ?? "attempted",
      confirmed: form.get("confirmed") === "on",
    });
  if (!parsed.success)
    return { error: "Confirm the action and provide its reason or recorded contact outcome." };
  const { kind, id, trip, note, outcome } = parsed.data;
  const api = createApiClient(await getSessionToken());
  try {
    if (kind === "contact")
      await api.POST("/api/v1/admin/manual-driver-contact-tasks/{task_id}/complete", {
        params: { path: { task_id: id } },
        body: { note, outcome },
      });
    else if (!trip) return { error: "The trip reference is missing. Reload the work list." };
    else if (kind === "apply")
      await api.POST("/api/v1/admin/trips/{trip_id}/quarantined-batches/{quarantine_id}/apply", {
        params: { path: { trip_id: trip, quarantine_id: id } },
        body: { note },
      });
    else
      await api.POST("/api/v1/admin/trips/{trip_id}/quarantined-batches/{quarantine_id}/discard", {
        params: { path: { trip_id: trip, quarantine_id: id } },
        body: { note },
      });
    revalidatePath(kind === "contact" ? "/admin/contact" : "/admin/late-data");
    return {
      done:
        kind === "contact"
          ? "Contact outcome recorded. This does not confirm provider delivery."
          : "Evidence decision recorded. Earnings and issued reports were not repriced or rewritten.",
    };
  } catch (error) {
    return {
      error:
        error instanceof ApiError
          ? error.message
          : "No result was confirmed. Reload or retry the same action and note.",
    };
  }
}
