"use client";

import { Button } from "@/components/ui/button";

export function PrintInvoiceButton() {
  return (
    <Button type="button" variant="ghost" className="print:hidden" onClick={() => window.print()}>
      Print or save as PDF
    </Button>
  );
}
