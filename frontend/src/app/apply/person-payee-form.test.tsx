import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
        if (url === "/api/apply/onboarding/uploads") {
          upload += 1;
          return Response.json({
            upload_id: `00000000-0000-4000-8000-00000000000${upload}`,
            upload: { url: `https://storage.test/${upload}`, fields: { key: `private-${upload}` } },
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
          return Response.json({ status: "pending_review", version: 1, masked_nin: "*******8901" });
        }
        throw new Error(`Unexpected request: ${url}`);
      }),
    );
  });

  it("uploads three private files, waits for clean scans and shows only masked identity", async () => {
    const user = userEvent.setup();
    render(<PersonPayeeForm />);
    await user.type(screen.getByLabelText("Onboarding access code"), ACCESS_TOKEN);
    await user.type(screen.getByLabelText("NIN"), "12345678901");
    await user.type(screen.getByLabelText("Verified account name"), "Test Driver");
    await user.type(screen.getByLabelText("Bank account number"), "0123456789");
    await user.type(screen.getByLabelText("Bank code"), "058");
    await user.upload(
      screen.getByLabelText("Driver licence"),
      new File(["licence"], "licence.png", { type: "image/png" }),
    );
    await user.upload(
      screen.getByLabelText("Driver photo"),
      new File(["photo"], "photo.png", { type: "image/png" }),
    );
    await user.upload(
      screen.getByLabelText("Signed agreement"),
      new File(["agreement"], "agreement.pdf", { type: "application/pdf" }),
    );
    await user.click(screen.getByRole("button", { name: "Submit person & payee evidence" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Person/payee evidence version 1 is pending review. NIN projection: *******8901.",
    );
    expect(screen.queryByText("12345678901")).not.toBeInTheDocument();
    expect(screen.queryByText("0123456789")).not.toBeInTheDocument();
    const calls = vi.mocked(fetch).mock.calls;
    const mutationBodies = calls
      .map(([, init]) => (typeof init?.body === "string" ? JSON.parse(init.body) : null))
      .filter(Boolean);
    expect(mutationBodies).toEqual(
      expect.arrayContaining([expect.objectContaining({ application_access_token: ACCESS_TOKEN })]),
    );
    expect(mutationBodies.some((body) => "application_reference" in body)).toBe(false);
  });
});
