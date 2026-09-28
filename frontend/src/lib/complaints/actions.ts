"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

export interface ComplaintActionState {
  error?: string;
  done?: string;
}

type Party = "driver" | "advertiser";

const BASE: Record<Party, string> = { driver: "/driver/help", advertiser: "/advertiser/help" };

const CATEGORIES = [
  "pay_or_payout",
  "trip_or_tracking",
  "campaign_or_job",
  "billing_or_invoice",
  "account",
  "other",
] as const;

const message = z
  .string()
  .trim()
  .min(1, "Write a message first")
  .max(2000, "Keep your message under 2,000 characters");

const raiseSchema = z.object({
  category: z.enum(CATEGORIES, { message: "Choose what your complaint is about" }),
  message,
  reference: z
    .string()
    .regex(/^((campaign|trip|payout):[0-9a-f-]{36})?$/i, "Choose a record from the list"),
  client_request_id: z.string().uuid(),
});

const followUpSchema = z.object({
  complaint_id: z.string().uuid(),
  message,
  client_request_id: z.string().uuid(),
});

const replySchema = followUpSchema.extend({ resolve: z.boolean() });

const updateSchema = z.object({
  complaint_id: z.string().uuid(),
  status: z.enum(["open", "resolved", ""]),
  assignee: z.union([z.literal(""), z.literal("none"), z.string().uuid()]),
});

function field(formData: FormData, name: string): string {
  return String(formData.get(name) ?? "");
}

function explain(error: unknown, notFound: string): ComplaintActionState {
  if (!(error instanceof ApiError)) {
    return { error: "Cardvert couldn't send this right now. Check your connection and try again." };
  }
  if (error.status === 401 || error.status === 403) {
    return { error: "Your session has ended. Sign in again, then try again." };
  }
  if (
    error.code === "ADVERTISER_ORGANIZATION_NOT_FOUND" ||
    error.code === "DRIVER_PROFILE_NOT_FOUND"
  ) {
    return { error: "Your account can't use Help right now. Sign in again, then try again." };
  }
  if (error.status === 404) return { error: notFound };
  if (error.code === "COMPLAINT_MESSAGE_LIMIT") {
    return { error: "This conversation is full. Please raise a new complaint instead." };
  }
  if (error.status === 409) {
    return { error: "This was already sent with different details. Refresh the page to see it." };
  }
  if (error.code === "COMPLAINT_ASSIGNEE_INVALID") {
    return { error: "Choose an active Terrax Media staff member." };
  }
  if (error.status === 422) {
    return { error: "Some details weren't accepted. Check them and try again." };
  }
  return { error: "Cardvert couldn't send this right now. Try again in a moment." };
}

async function raise(party: Party, formData: FormData): Promise<ComplaintActionState> {
  const parsed = raiseSchema.safeParse({
    category: field(formData, "category"),
    message: field(formData, "message"),
    reference: field(formData, "reference"),
    client_request_id: field(formData, "client_request_id"),
  });
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Check the form" };
  const { reference, ...rest } = parsed.data;
  const [referenceType, referenceId] = reference ? reference.split(":") : [];
  const body = {
    ...rest,
    ...(referenceType
      ? {
          reference_type: referenceType as "campaign" | "trip" | "payout",
          reference_id: referenceId,
        }
      : {}),
  };
  const api = createApiClient(await getSessionToken());
  let complaintId: string;
  try {
    const path = party === "driver" ? "/api/v1/driver/complaints" : "/api/v1/advertiser/complaints";
    const { data } = await api.POST(path, { body });
    if (!data) return explain(undefined, "");
    complaintId = data.id;
  } catch (error) {
    return explain(
      error,
      "We couldn't find that record in your account. Choose another one or leave it out.",
    );
  }
  revalidatePath(BASE[party]);
  redirect(`${BASE[party]}/${complaintId}`);
}

async function followUp(party: Party, formData: FormData): Promise<ComplaintActionState> {
  const parsed = followUpSchema.safeParse({
    complaint_id: field(formData, "complaint_id"),
    message: field(formData, "message"),
    client_request_id: field(formData, "client_request_id"),
  });
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Check the form" };
  const { complaint_id, ...body } = parsed.data;
  const api = createApiClient(await getSessionToken());
  try {
    const options = { params: { path: { complaint_id } }, body };
    if (party === "driver") {
      await api.POST("/api/v1/driver/complaints/{complaint_id}/messages", options);
    } else {
      await api.POST("/api/v1/advertiser/complaints/{complaint_id}/messages", options);
    }
  } catch (error) {
    return explain(error, "This complaint couldn't be found.");
  }
  revalidatePath(`${BASE[party]}/${complaint_id}`);
  return { done: "Sent. Customer Service will reply here." };
}

export async function raiseDriverComplaintAction(
  _prev: ComplaintActionState,
  formData: FormData,
): Promise<ComplaintActionState> {
  return raise("driver", formData);
}

export async function raiseAdvertiserComplaintAction(
  _prev: ComplaintActionState,
  formData: FormData,
): Promise<ComplaintActionState> {
  return raise("advertiser", formData);
}

export async function followUpDriverComplaintAction(
  _prev: ComplaintActionState,
  formData: FormData,
): Promise<ComplaintActionState> {
  return followUp("driver", formData);
}

export async function followUpAdvertiserComplaintAction(
  _prev: ComplaintActionState,
  formData: FormData,
): Promise<ComplaintActionState> {
  return followUp("advertiser", formData);
}

export async function replyToComplaintAction(
  _prev: ComplaintActionState,
  formData: FormData,
): Promise<ComplaintActionState> {
  const parsed = replySchema.safeParse({
    complaint_id: field(formData, "complaint_id"),
    message: field(formData, "message"),
    client_request_id: field(formData, "client_request_id"),
    resolve: formData.get("resolve") === "on",
  });
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Check the form" };
  const { complaint_id, ...body } = parsed.data;
  const api = createApiClient(await getSessionToken());
  try {
    await api.POST("/api/v1/admin/complaints/{complaint_id}/messages", {
      params: { path: { complaint_id } },
      body,
    });
  } catch (error) {
    return explain(error, "This complaint couldn't be found.");
  }
  revalidatePath("/admin/complaints");
  revalidatePath(`/admin/complaints/${complaint_id}`);
  return { done: body.resolve ? "Reply sent and complaint resolved." : "Reply sent." };
}

export async function updateComplaintAction(
  _prev: ComplaintActionState,
  formData: FormData,
): Promise<ComplaintActionState> {
  const parsed = updateSchema.safeParse({
    complaint_id: field(formData, "complaint_id"),
    status: field(formData, "status"),
    assignee: field(formData, "assignee"),
  });
  if (!parsed.success) return { error: "Choose a status or a staff member." };
  const { complaint_id, status, assignee } = parsed.data;
  const body: { status?: "open" | "resolved"; assigned_to_user_id?: string | null } = {};
  if (status) body.status = status;
  if (assignee === "none") body.assigned_to_user_id = null;
  else if (assignee) body.assigned_to_user_id = assignee;
  const api = createApiClient(await getSessionToken());
  try {
    await api.PATCH("/api/v1/admin/complaints/{complaint_id}", {
      params: { path: { complaint_id } },
      body,
    });
  } catch (error) {
    return explain(error, "This complaint couldn't be found.");
  }
  revalidatePath("/admin/complaints");
  revalidatePath(`/admin/complaints/${complaint_id}`);
  return { done: "Saved." };
}
