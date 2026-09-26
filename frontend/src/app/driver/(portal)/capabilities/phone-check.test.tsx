import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { EMPTY_CAPABILITY_SNAPSHOT, type CapabilitySnapshot } from "@/lib/pwa/capability-contract";

const probes = vi.hoisted(() => ({
  snapshot: {} as CapabilitySnapshot,
  checkAll: vi.fn(),
}));
vi.mock("./use-capability-probes", async () => {
  const { assessPilotPwa } = await vi.importActual<typeof import("@/lib/pwa/capability-contract")>(
    "@/lib/pwa/capability-contract",
  );
  return {
    useCapabilityProbes: () => ({
      snapshot: probes.snapshot,
      passiveReady: true,
      busy: null,
      notice: "Run each probe on the test device.",
      assessment: assessPilotPwa(probes.snapshot),
      report: '{"contractVersion":"r14-a-v2"}',
      checkAll: probes.checkAll,
    }),
  };
});

import { PhoneCheck } from "./phone-check";
import DriverCapabilityPage from "./page";

function row(label: string) {
  return screen.getByText(label).closest("li") as HTMLElement;
}

describe("driver Phone check (D38b)", () => {
  beforeEach(() => {
    probes.snapshot = {
      ...EMPTY_CAPABILITY_SNAPSHOT,
      secureContext: true,
      manifestLinked: true,
      displayMode: "browser",
    };
    probes.checkAll.mockReset().mockResolvedValue(undefined);
  });

  it("shows plain yes/no rows and no probe codes or raw report", async () => {
    const { rerender } = render(<PhoneCheck />);

    expect(screen.getByRole("heading", { name: "Phone check" })).toBeInTheDocument();
    // Installation is observed passively; the others wait for the explicit press.
    expect(within(row("Cardvert is on your home screen")).getByText("No")).toBeInTheDocument();
    expect(within(row("Location is allowed")).getByText("Not checked yet")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/R14-A|LOCATION_UNPROBED|contractVersion/);

    probes.snapshot = {
      ...probes.snapshot,
      location: "denied",
      wakeLock: "pass",
      indexedDb: "pass",
      durableQueue: "pass",
      webLocks: "pass",
      session: "valid",
    };
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "Check this phone" })),
    );
    rerender(<PhoneCheck />);

    expect(probes.checkAll).toHaveBeenCalledOnce();
    expect(within(row("Location is allowed")).getByText("No")).toBeInTheDocument();
    expect(screen.getByText(/Allow location for Cardvert/)).toBeInTheDocument();
    for (const label of [
      "The screen can stay on",
      "Trips can be saved on this phone",
      "You're signed in",
    ]) {
      expect(within(row(label)).getByText("Yes")).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: "Check again" })).toBeInTheDocument();
  });

  it("copies the redacted report for support and says when copying fails", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    render(<PhoneCheck />);

    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "Copy for support" })),
    );
    expect(writeText).toHaveBeenCalledWith('{"contractVersion":"r14-a-v2"}');
    expect(screen.getByRole("status")).toHaveTextContent("Copied");

    Object.defineProperty(navigator, "clipboard", { configurable: true, value: undefined });
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "Copy for support" })),
    );
    expect(screen.getByRole("status")).toHaveTextContent("Couldn't copy on this phone");
  });

  it("keeps the R14-A probe on the unlinked support view only", async () => {
    const { unmount } = render(await DriverCapabilityPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("heading", { name: "Phone check" })).toBeInTheDocument();
    unmount();

    render(await DriverCapabilityPage({ searchParams: Promise.resolve({ view: "support" }) }));
    expect(
      screen.getByRole("heading", { name: "Production PWA capability probe" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("capability-location")).toHaveTextContent("LOCATION_UNPROBED");
  });
});
