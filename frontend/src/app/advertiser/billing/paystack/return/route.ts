import { type NextRequest, NextResponse } from "next/server";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

const REFERENCE = /^[A-Za-z0-9.=-]{1,100}$/;

export async function GET(request: NextRequest) {
  const reference = request.nextUrl.searchParams.get("reference")?.trim() ?? "";
  const transactionReference = request.nextUrl.searchParams.get("trxref")?.trim() ?? "";
  const destination = new URL("/advertiser/billing", request.url);
  if (
    !REFERENCE.test(reference) ||
    (transactionReference !== "" && transactionReference !== reference)
  ) {
    destination.searchParams.set("payment", "error");
    destination.searchParams.set("message", "Paystack returned an invalid payment reference.");
    return NextResponse.redirect(destination);
  }
  try {
    const api = createApiClient(await getSessionToken());
    const { data } = await api.POST("/api/v1/advertiser/payment-checkouts/{reference}/verify", {
      params: { path: { reference } },
    });
    destination.searchParams.set(
      "payment",
      data?.status === "confirmed" ? "confirmed" : data?.status === "failed" ? "failed" : "pending",
    );
  } catch (caught) {
    destination.searchParams.set(
      "payment",
      caught instanceof ApiError && caught.code === "PAYMENT_NOT_FINAL" ? "pending" : "error",
    );
    if (!(caught instanceof ApiError && caught.code === "PAYMENT_NOT_FINAL")) {
      destination.searchParams.set(
        "message",
        "Cardvert could not verify this payment yet. No unverified payment was applied.",
      );
    }
  }
  return NextResponse.redirect(destination);
}
