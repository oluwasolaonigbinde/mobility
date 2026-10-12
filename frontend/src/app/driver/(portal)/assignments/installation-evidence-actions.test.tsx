import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  upload: vi.fn(),
  postJson: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: mocks.refresh }) }));
vi.mock("@/lib/files/installation-evidence-upload", () => ({
  uploadInstallationImage: mocks.upload,
  postJson: mocks.postJson,
}));

import { InstallationEvidenceActions } from "./installation-evidence-actions";

const ASSIGNMENT_ID = "00000000-0000-4000-8000-000000000001";

describe("InstallationEvidenceActions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    const values = new Map<string, string>();
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        clear: () => values.clear(),
        getItem: (key: string) => values.get(key) ?? null,
        setItem: (key: string, value: string) => values.set(key, value),
      },
    });
    window.localStorage.setItem(
      "cardvert-installation-device-id",
      "00000000-0000-4000-8000-000000000002",
    );
  });

  it("uploads every configured view before submitting one bound revision", async () => {
    const user = userEvent.setup();
    mocks.upload.mockResolvedValueOnce("front-file").mockResolvedValueOnce("close-file");
    mocks.postJson.mockResolvedValue({ id: "submission" });
    const { container } = render(
      <InstallationEvidenceActions
        assignmentId={ASSIGNMENT_ID}
        status="accepted"
        requiredViews={["front", "close_up"]}
      />,
    );
    const inputs = container.querySelectorAll<HTMLInputElement>('input[type="file"]');
    await user.upload(inputs[0]!, new File(["front"], "front.png", { type: "image/png" }));
    await user.upload(inputs[1]!, new File(["close"], "close.png", { type: "image/png" }));
    await user.click(screen.getByRole("button", { name: "Send installation photos" }));

    await waitFor(() => expect(mocks.postJson).toHaveBeenCalledTimes(1));
    expect(mocks.upload).toHaveBeenCalledTimes(2);
    expect(mocks.postJson).toHaveBeenCalledWith(
      `/api/driver/assignments/${ASSIGNMENT_ID}/installation-evidence`,
      expect.objectContaining({
        device_id: "00000000-0000-4000-8000-000000000002",
        photos: [
          { view: "front", stored_file_id: "front-file" },
          { view: "close_up", stored_file_id: "close-file" },
        ],
      }),
    );
    expect(await screen.findByText("✓ Photos sent to Terrax Media for review.")).toBeVisible();
  });

  it("asks for new photos when the approved ones have expired", () => {
    render(
      <InstallationEvidenceActions
        assignmentId={ASSIGNMENT_ID}
        status="active"
        requiredViews={["front"]}
        latestEvidenceStatus="expired"
      />,
    );

    expect(screen.getByText(/New photos are due/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Send installation photos" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Send display photo" })).not.toBeInTheDocument();
  });

  it("gets a nonce before uploading and consuming a start-of-shift proof", async () => {
    const user = userEvent.setup();
    mocks.upload.mockResolvedValue("proof-file");
    mocks.postJson
      .mockResolvedValueOnce({ challenge_id: "challenge", nonce: "server-nonce" })
      .mockResolvedValueOnce({ id: "proof" });
    const { container } = render(
      <InstallationEvidenceActions
        assignmentId={ASSIGNMENT_ID}
        status="active"
        requiredViews={["front"]}
        latestEvidenceStatus="approved"
      />,
    );
    const inputs = container.querySelectorAll<HTMLInputElement>('input[type="file"]');
    const proofInput = inputs[inputs.length - 1]!;
    await user.upload(proofInput, new File(["proof"], "proof.png", { type: "image/png" }));
    await user.click(screen.getByRole("button", { name: "Send display photo" }));

    await waitFor(() => expect(mocks.postJson).toHaveBeenCalledTimes(2));
    expect(mocks.postJson).toHaveBeenNthCalledWith(
      1,
      `/api/driver/assignments/${ASSIGNMENT_ID}/display-proof/challenge`,
      { device_id: "00000000-0000-4000-8000-000000000002" },
    );
    expect(mocks.postJson).toHaveBeenNthCalledWith(
      2,
      `/api/driver/assignments/${ASSIGNMENT_ID}/display-proof`,
      expect.objectContaining({
        challenge_id: "challenge",
        nonce: "server-nonce",
        stored_file_id: "proof-file",
      }),
    );
  });

  it("surfaces a requested display photo in plain words", () => {
    render(
      <InstallationEvidenceActions
        assignmentId={ASSIGNMENT_ID}
        status="active"
        requiredViews={["front"]}
        latestEvidenceStatus="approved"
        pendingChallengeDueAt="2026-08-27T12:00:00Z"
      />,
    );

    expect(screen.getByText(/Terrax Media asked for a new photo/)).toBeVisible();
    expect(screen.queryByText(/GPS/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send display photo" })).toBeVisible();
  });

  it("names the client's photo views and hides display proof until its windows are set", async () => {
    render(
      <InstallationEvidenceActions
        assignmentId={ASSIGNMENT_ID}
        status="active"
        requiredViews={["front", "back", "left", "right", "close_up"]}
        latestEvidenceStatus="approved"
        proofAvailable={false}
      />,
    );

    expect(
      screen.queryByRole("button", { name: "Send installation photos" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send new photos" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send display photo" })).not.toBeInTheDocument();
  });
});
