import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/auth/actions", () => ({ signOutAction: vi.fn() }));

import { signOutAction } from "@/lib/auth/actions";
import { DriverLogoutButton, handleSessionLogoutMessage, runSignOutFlow } from "./logout-button";

class FakeBroadcastChannel {
  static instances: FakeBroadcastChannel[] = [];
  onmessage: ((event: MessageEvent) => void) | null = null;
  postMessage = vi.fn((data: unknown) => {
    for (const channel of FakeBroadcastChannel.instances) {
      if (channel !== this) {
        channel.onmessage?.({ data } as MessageEvent);
      }
    }
  });
  close = vi.fn();

  constructor(public readonly name: string) {
    FakeBroadcastChannel.instances.push(this);
  }
}

describe("multi-tab logout", () => {
  afterEach(() => {
    FakeBroadcastChannel.instances = [];
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("stops tracker state before a receiving tab navigates", () => {
    const order: string[] = [];
    window.addEventListener("cardvert-driver-logout", () => order.push("stop"), {
      once: true,
    });
    const navigate = vi.fn(() => order.push("navigate"));

    act(() => {
      expect(
        handleSessionLogoutMessage(
          { type: "logout", sender: "other-tab" },
          "receiving-tab",
          navigate,
        ),
      ).toBe(true);
    });

    expect(order).toEqual(["stop", "navigate"]);
    expect(navigate).toHaveBeenCalledWith("/login");
  });

  it("listens for logout without rebroadcasting", () => {
    vi.stubGlobal("BroadcastChannel", FakeBroadcastChannel);
    render(<DriverLogoutButton />);

    const receivingChannel = FakeBroadcastChannel.instances[0]!;
    expect(receivingChannel.name).toBe("cardvert-driver-session");
    expect(receivingChannel.onmessage).toBeTypeOf("function");
    expect(receivingChannel.postMessage).not.toHaveBeenCalled();
  });

  it("broadcasts only after global revocation is confirmed", async () => {
    vi.stubGlobal("BroadcastChannel", FakeBroadcastChannel);
    const trackerStop = vi.fn();
    window.addEventListener("cardvert-driver-logout", trackerStop);
    const navigate = vi.fn();

    await expect(
      runSignOutFlow(
        vi.fn().mockResolvedValue({
          globalRevocationConfirmed: true,
          globalRevocationFailed: false,
        }),
        navigate,
      ),
    ).resolves.toBeUndefined();

    const sent = FakeBroadcastChannel.instances.at(-1)?.postMessage.mock.calls[0]?.[0] as {
      type: string;
      sender: string;
    };
    expect(sent.type).toBe("logout");
    expect(sent.sender).toBeTruthy();
    expect(trackerStop).toHaveBeenCalledOnce();
    expect(navigate).toHaveBeenCalledWith("/login");
    window.removeEventListener("cardvert-driver-logout", trackerStop);
  });

  it("keeps an unconfirmed outage local and reports it inline", async () => {
    vi.stubGlobal("BroadcastChannel", FakeBroadcastChannel);
    const navigate = vi.fn();

    await expect(
      runSignOutFlow(
        vi.fn().mockResolvedValue({
          globalRevocationConfirmed: false,
          globalRevocationFailed: true,
        }),
        navigate,
      ),
    ).resolves.toBe("Sign-out on every device could not be confirmed. Please try again.");

    expect(FakeBroadcastChannel.instances).toHaveLength(0);
    expect(navigate).not.toHaveBeenCalled();

    vi.mocked(signOutAction).mockResolvedValue({
      globalRevocationConfirmed: false,
      globalRevocationFailed: true,
    });
    render(<DriverLogoutButton />);
    fireEvent.submit(screen.getByRole("button", { name: "Exit" }).closest("form")!);
    expect(
      await screen.findByText("Sign-out on every device could not be confirmed. Please try again."),
    ).toHaveAttribute("role", "alert");
  });
});
