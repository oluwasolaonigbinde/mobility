"use client";
import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { convertEnquiry, type EnquiryConversionState } from "./actions";

export function ConvertEnquiryForm({ enquiryId }: { enquiryId: string }) {
  const [state, action, pending] = useActionState(
    convertEnquiry.bind(null, enquiryId),
    {} as EnquiryConversionState,
  );
  return (
    <form action={action} className="mt-5">
      <Button type="submit" disabled={pending}>
        {pending ? "Creating…" : "Create advertiser"}
      </Button>
      {state.error ? (
        <p role="alert" className="text-coral mt-3 text-sm">
          {state.error}
        </p>
      ) : null}
    </form>
  );
}
