import { type NextRequest, NextResponse } from "next/server";
import { createApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";

const REFERENCE = /^[A-Za-z0-9.=-]{1,100}$/;

// Only fixed codes travel back to the billing page; it maps them to its own copy.
export async function GET(request: NextRequest) {
  const reference = request.nextUrl.searchParams.get("reference")?.trim() ?? "";
  const transactionReference = request.nextUrl.searchParams.get("trxref")?.trim() ?? "";
  const destination = new URL("/advertiser/billing", request.url);
  if (
    !REFERENCE.test(reference) ||
    (transactionReference !== "" && transactionReference !== reference)
  ) {
    destination.searchParams.set("payment", "error");
    destination.searchParams.set("code", "payment_not_found");
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
    if (caught instanceof ApiError && caught.code === "PAYMENT_NOT_FINAL") {
      destination.searchParams.set("payment", "pending");
    } else {
      destination.searchParams.set("payment", "error");
      destination.searchParams.set(
        "code",
        caught instanceof ApiError && caught.code === "PAYMENT_CHECKOUT_NOT_FOUND"
          ? "payment_not_found"
          : "payment_unconfirmed",
      );
    }
  }
  return NextResponse.redirect(destination);
}
