"use server";

import { unstable_rethrow } from "next/navigation";

import { publicActionError } from "@/lib/api/public-action-error";
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
  if (error instanceof ApiError)
    return {
      error: publicActionError(error, {
        PAYOUT_AUTOMATIC_ALREADY_PAUSED: "Automatic payouts are already paused",
        PAYOUT_AUTOMATIC_NOT_PAUSED: "Automatic payouts are not paused",
        PAYOUT_AUTOMATIC_ALERT_RESOLVED: "This alert is already followed up",
      }),
    };
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
    unstable_rethrow(error);
    return failure(error);
  }
  revalidatePath("/admin/money");
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
    const count = data?.released_count;
    if (typeof count !== "number" || !Number.isSafeInteger(count) || count < 0) {
      return { error: "No result was confirmed. Reload before trying again." };
    }
    revalidatePath("/admin/money");
    return {
      done:
        count === 0
          ? "There were no unsent automatic payments to move."
          : `${count} unsent payment${count === 1 ? "" : "s"} moved to manual review.`,
    };
  } catch (error) {
    unstable_rethrow(error);
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
    unstable_rethrow(error);
    return failure(error);
  }
  revalidatePath("/admin/money");
  return { done: "Marked as followed up." };
}
