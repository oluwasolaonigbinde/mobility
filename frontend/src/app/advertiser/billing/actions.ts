"use server";

import { redirect } from "next/navigation";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";
import { publicActionError } from "@/lib/api/public-action-error";
import { getSessionToken } from "@/lib/auth/session";

const checkoutSchema = z.object({ invoiceId: z.string().uuid() });

export async function startInvoicePayment(formData: FormData): Promise<never> {
  const parsed = checkoutSchema.safeParse({ invoiceId: formData.get("invoiceId") });
  if (!parsed.success) {
    redirect("/advertiser/billing?payment=error&message=Choose+a+valid+invoice.");
  }
  let destination: string | null = null;
  let error: string | null = null;
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.POST("/api/v1/advertiser/invoices/{invoice_id}/checkout", {
      params: { path: { invoice_id: parsed.data.invoiceId } },
    });
    destination = data?.checkout_url ?? null;
    if (!destination) {
      error = "Paystack is still preparing this checkout. Please try again.";
    }
  } catch (caught) {
    error = publicActionError(
      caught,
      {},
      "Cardvert could not open Paystack. No payment was taken.",
    );
  }
  if (destination) redirect(destination);
  redirect(
    `/advertiser/billing?payment=error&message=${encodeURIComponent(error ?? "Checkout unavailable")}`,
  );
}
