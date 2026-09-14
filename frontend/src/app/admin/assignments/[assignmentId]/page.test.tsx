import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AssignmentReadiness from "./page";

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("../activate-button", () => ({
  ActivateAssignmentButton: () => <button>Activate assignment</button>,
}));

const props = { params: Promise.resolve({ assignmentId: "assignment" }) };

describe("assignment activation readiness", () => {
  beforeEach(() => mocks.get.mockReset());

  it("offers activation only when the server reports readiness", async () => {
    mocks.get.mockResolvedValue({
      data: { assignment_id: "assignment", ready: true, blocker_code: null, message: "Ready." },
    });
    render(await AssignmentReadiness(props));
    expect(screen.getByRole("heading", { name: "Ready for final activation" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Activate assignment" })).toBeTruthy();
  });

  it("does not invite a second activation for an already-active assignment", async () => {
    mocks.get.mockResolvedValue({
      data: {
        assignment_id: "assignment",
        ready: false,
        blocker_code: "ASSIGNMENT_ALREADY_ACTIVE",
        message: "This assignment is already active. No activation is needed.",
      },
    });
    render(await AssignmentReadiness(props));
    expect(screen.getByRole("heading", { name: "Already active" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Activate assignment" })).toBeNull();
    expect(screen.queryByText("Review funding with finance")).toBeNull();
  });
});
