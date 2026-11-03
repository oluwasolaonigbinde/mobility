"use server";

import { redirect, unstable_rethrow } from "next/navigation";
import { z } from "zod";
import { createApiClient } from "@/lib/api/client";

import { getSessionToken } from "@/lib/auth/session";

const checkoutSchema = z.object({ invoiceId: z.string().uuid() });

export async function startInvoicePayment(formData: FormData): Promise<never> {
  const parsed = checkoutSchema.safeParse({ invoiceId: formData.get("invoiceId") });
  if (!parsed.success) {
    redirect("/advertiser/billing?payment=error&code=invalid_invoice");
  }
  let destination: string | null = null;

  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.POST("/api/v1/advertiser/invoices/{invoice_id}/checkout", {
      params: { path: { invoice_id: parsed.data.invoiceId } },
    });
    destination =
      data?.status === "confirmed" || data?.status === "failed"
        ? `/advertiser/billing?payment=${data.status}`
        : (data?.checkout_url ?? null);
  } catch (caught) {
    unstable_rethrow(caught);
  }
  if (destination) redirect(destination);
  redirect("/advertiser/billing?payment=error&code=checkout_unavailable");
}
