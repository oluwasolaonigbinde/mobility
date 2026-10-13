import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PersonPayeeForm } from "./person-payee-form";

const ACCESS_TOKEN = "application-access-capability-secret";

describe("PersonPayeeForm", () => {
  beforeEach(() => {
    vi.stubGlobal("crypto", {
      randomUUID: vi.fn(() => "00000000-0000-4000-8000-0000000000aa"),
      subtle: { digest: vi.fn(async () => new Uint8Array(32).buffer) },
    });
    let upload = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/apply/onboarding/banks")
          return Response.json([{ code: "058", name: "GTBank" }]);
        if (url === "/api/apply/onboarding/account-name")
          return Response.json({
            outcome: "unavailable",
            bank_check_receipt: "fallback-receipt",
          });
        if (url === "/api/apply/onboarding/uploads") {
          upload += 1;
          return Response.json({
            upload_id: `00000000-0000-4000-8000-00000000000${upload}`,
            upload: {
              url: `https://storage.test/${upload}`,
              fields: { key: `private-${upload}` },
            },
          });
        }
        if (url.startsWith("https://storage.test/")) return new Response(null, { status: 204 });
        if (url.includes("/confirm")) {
          return Response.json({
            id: `00000000-0000-4000-8000-00000000001${upload}`,
            scan_status: "pending",
          });
        }
        if (url.includes("/status")) {
          return Response.json({ id: "safe-file", scan_status: "clean" });
        }
        if (url === "/api/apply/onboarding/person-payee") {
          return Response.json({
            status: "pending_review",
            version: 1,
            masked_nin: "*******8901",
          });
        }
        throw new Error(`Unexpected request: ${url}`);
      }),
    );
  });

  it("uploads two private files and records consent, waits for clean scans and never echoes identity", async () => {
    render(<PersonPayeeForm />);
    expect(screen.queryByLabelText("Signed agreement")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Read the full agreement" })).toHaveAttribute(
      "href",
      "/apply/agreement/1",
    );
    fireEvent.change(screen.getByLabelText("Code from your email"), {
      target: { value: ACCESS_TOKEN },
    });
    fireEvent.change(screen.getByLabelText("NIN (11 digits)"), {
      target: { value: "12345678901" },
    });
    fireEvent.change(screen.getByLabelText("Account number (10 digits)"), {
      target: { value: "0123456789" },
    });
    await screen.findByRole("option", { name: "GTBank" });
    fireEvent.change(screen.getByLabelText("Bank"), {
      target: { value: "058" },
    });
    fireEvent.change(await screen.findByLabelText("Name on bank account"), {
      target: { value: "Test Driver" },
    });
    fireEvent.click(screen.getByLabelText("I agree"));
    fireEvent.change(screen.getByLabelText("Driver's licence"), {
      target: {
        files: [new File(["licence"], "licence.png", { type: "image/png" })],
      },
    });
    fireEvent.change(screen.getByLabelText("Photo of you"), {
      target: {
        files: [new File(["photo"], "photo.png", { type: "image/png" })],
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send my details" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Sent. We'll check your details. Check your status with your application reference.",
    );
    expect(screen.queryByText(/\*{7}8901/)).not.toBeInTheDocument();
    expect(screen.queryByText("12345678901")).not.toBeInTheDocument();
    expect(screen.queryByText("0123456789")).not.toBeInTheDocument();
    const calls = vi.mocked(fetch).mock.calls;
    const mutationBodies = calls
      .map(([, init]) => (typeof init?.body === "string" ? JSON.parse(init.body) : null))
      .filter(Boolean);
    expect(mutationBodies).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          application_access_token: ACCESS_TOKEN,
          agreement_version: "1",
          agreement_accepted: true,
          bank_check_receipt: "fallback-receipt",
        }),
      ]),
    );
    expect(mutationBodies.some((body) => "application_reference" in body)).toBe(false);
  });
});
