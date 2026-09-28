"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

export interface AutomaticActionState {
  error?: string;
  done?: string;
}

const reason = z
  .string()
  .trim()
  .min(3, "Give a reason of at least 3 characters — it is kept in the audit trail")
  .max(500, "Keep the reason under 500 characters");

const switchSchema = z.object({ intent: z.enum(["pause", "resume"]), reason });
const releaseSchema = z.object({ reason });
const resolveSchema = z.object({ alert_id: z.string().uuid(), note: reason });

function failure(error: unknown): AutomaticActionState {
  if (error instanceof ApiError) return { error: error.message };
  return { error: "Could not reach the server. Try again." };
}

export async function switchAutomaticPayoutsAction(
  _prev: AutomaticActionState,
  formData: FormData,
): Promise<AutomaticActionState> {
  const parsed = switchSchema.safeParse({
    intent: formData.get("intent"),
    reason: String(formData.get("reason") ?? ""),
  });
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Check the form" };
  const api = createApiClient(await getSessionToken());
  try {
    if (parsed.data.intent === "pause") {
      await api.POST("/api/v1/admin/payouts/automatic/pause", {
        body: { reason: parsed.data.reason },
      });
    } else {
      await api.POST("/api/v1/admin/payouts/automatic/resume", {
        body: { reason: parsed.data.reason },
      });
    }
  } catch (error) {
    return failure(error);
  }
  revalidatePath("/admin/payouts/automatic");
  return {
    done:
      parsed.data.intent === "pause"
        ? "Automatic payouts are paused."
        : "Automatic payouts are running again.",
  };
}

export async function releaseUnsentAction(
  _prev: AutomaticActionState,
  formData: FormData,
): Promise<AutomaticActionState> {
  const parsed = releaseSchema.safeParse({ reason: String(formData.get("reason") ?? "") });
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Check the form" };
  const api = createApiClient(await getSessionToken());
  try {
    const { data } = await api.POST("/api/v1/admin/payouts/automatic/release-unsent", {
      body: { reason: parsed.data.reason },
    });
    revalidatePath("/admin/payouts/automatic");
    const count = data?.released_count ?? 0;
    return {
      done:
        count === 0
          ? "There were no unsent automatic payments to move."
          : `${count} unsent payment${count === 1 ? "" : "s"} moved to manual review.`,
    };
  } catch (error) {
    return failure(error);
  }
}

export async function resolveAlertAction(
  _prev: AutomaticActionState,
  formData: FormData,
): Promise<AutomaticActionState> {
  const parsed = resolveSchema.safeParse({
    alert_id: formData.get("alert_id"),
    note: String(formData.get("note") ?? ""),
  });
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Check the form" };
  const api = createApiClient(await getSessionToken());
  try {
    await api.POST("/api/v1/admin/payouts/automatic/alerts/{alert_id}/resolve", {
      params: { path: { alert_id: parsed.data.alert_id } },
      body: { note: parsed.data.note },
    });
  } catch (error) {
    return failure(error);
  }
  revalidatePath("/admin/payouts/automatic");
  return { done: "Marked as followed up." };
}
