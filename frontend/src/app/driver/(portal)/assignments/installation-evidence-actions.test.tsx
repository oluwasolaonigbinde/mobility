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

  it("names only the missing views before any upload", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <InstallationEvidenceActions
        assignmentId={ASSIGNMENT_ID}
        status="accepted"
        requiredViews={["front", "back", "close_up"]}
      />,
    );
    await user.upload(
      container.querySelector<HTMLInputElement>('input[type="file"]')!,
      new File(["front"], "front.png", { type: "image/png" }),
    );
    await user.click(screen.getByRole("button", { name: "Send installation photos" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Back");
    expect(alert).toHaveTextContent("Close");
    expect(alert).not.toHaveTextContent("Front");
    expect(mocks.upload).not.toHaveBeenCalled();
    expect(mocks.postJson).not.toHaveBeenCalled();
  });

  it("has no daily photo task after weekly photos are approved", async () => {
    render(
      <InstallationEvidenceActions
        assignmentId={ASSIGNMENT_ID}
        status="active"
        requiredViews={["front", "back", "left", "right", "close_up"]}
        latestEvidenceStatus="approved"
      />,
    );

    expect(
      screen.queryByRole("button", { name: "Send installation photos" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send new photos" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send display photo" })).not.toBeInTheDocument();
  });
});
it.each(["approved", "pending_review"])(
  "does not show an old rejection reason for %s photos",
  (status) => {
    render(
      <InstallationEvidenceActions
        assignmentId={ASSIGNMENT_ID}
        status="accepted"
        requiredViews={["front"]}
        latestEvidenceStatus={status}
        rejectionReason="Old reason"
      />,
    );
    expect(screen.queryByText("Old reason")).toBeNull();
  },
);
it("shows the saved rejection as plain text before retaking photos", () => {
  const reason = "<strong>Retake the branding close-up.</strong>";
  const { container } = render(
    <InstallationEvidenceActions
      assignmentId={ASSIGNMENT_ID}
      status="accepted"
      requiredViews={["front"]}
      latestEvidenceStatus="rejected"
      rejectionReason={reason}
    />,
  );
  const message = screen.getByText(reason);
  expect(message).toBeVisible();
  expect(container.querySelector("strong")).toBeNull();
  expect(
    message.compareDocumentPosition(container.querySelector('input[type="file"]')!) &
      Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
});
it("keeps a useful fallback when a rejected revision has no reason", () => {
  render(
    <InstallationEvidenceActions
      assignmentId={ASSIGNMENT_ID}
      status="accepted"
      requiredViews={["front"]}
      latestEvidenceStatus="rejected"
    />,
  );
  expect(screen.getByText(/Your last photos weren't approved/)).toBeVisible();
  expect(screen.getByRole("button", { name: "Send installation photos" })).toBeVisible();
});
