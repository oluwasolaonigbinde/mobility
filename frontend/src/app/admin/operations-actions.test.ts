import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({ POST: vi.fn(), revalidatePath: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ POST: mocks.POST }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "operator-token" }));
vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));

import { resolveOperation } from "./operations-actions";

const TASK = "11111111-1111-4111-8111-111111111111";
const TRIP = "22222222-2222-4222-8222-222222222222";

function form(values: Record<string, string>) {
  const data = new FormData();
  for (const [key, value] of Object.entries(values)) data.set(key, value);
  return data;
}

describe("resolveOperation", () => {
  beforeEach(() => vi.resetAllMocks());

  it.each([
    ["an unconfirmed action", { kind: "contact", id: TASK, note: "Called", outcome: "reached" }],
    [
      "a blank note",
      { kind: "contact", id: TASK, note: "   ", outcome: "reached", confirmed: "on" },
    ],
    ["an unknown kind", { kind: "delete", id: TASK, note: "x", confirmed: "on" }],
    ["a malformed id", { kind: "apply", id: "task", trip: TRIP, note: "x", confirmed: "on" }],
    [
      "an unknown outcome",
      { kind: "contact", id: TASK, note: "x", outcome: "sent", confirmed: "on" },
    ],
  ])("rejects %s without calling the API", async (_label, values) => {
    expect(await resolveOperation({}, form(values))).toEqual({
      error: "Confirm the action and provide its reason or recorded contact outcome.",
    });
    expect(mocks.POST).not.toHaveBeenCalled();
    expect(mocks.revalidatePath).not.toHaveBeenCalled();
  });

  it("records a contact outcome without claiming provider delivery", async () => {
    mocks.POST.mockResolvedValue({ data: {} });
    const result = await resolveOperation(
      {},
      form({
        kind: "contact",
        id: TASK,
        note: "  Reached driver  ",
        outcome: "reached",
        confirmed: "on",
      }),
    );
    expect(mocks.POST).toHaveBeenCalledExactlyOnceWith(
      "/api/v1/admin/manual-driver-contact-tasks/{task_id}/complete",
      { params: { path: { task_id: TASK } }, body: { note: "Reached driver", outcome: "reached" } },
    );
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/admin/contact");
    expect(result).toEqual({
      done: "Contact outcome recorded. This does not confirm provider delivery.",
    });
  });

  it("defaults a missing contact outcome to an attempt", async () => {
    mocks.POST.mockResolvedValue({ data: {} });
    await resolveOperation(
      {},
      form({ kind: "contact", id: TASK, note: "Voicemail", confirmed: "on" }),
    );
    expect(mocks.POST.mock.calls[0]![1].body).toEqual({ note: "Voicemail", outcome: "attempted" });
  });

  it("refuses an evidence decision without its trip reference", async () => {
    expect(
      await resolveOperation({}, form({ kind: "apply", id: TASK, note: "Valid", confirmed: "on" })),
    ).toEqual({ error: "The trip reference is missing. Reload the work list." });
    expect(mocks.POST).not.toHaveBeenCalled();
    expect(mocks.revalidatePath).not.toHaveBeenCalled();
  });

  it.each(["apply", "discard"] as const)(
    "sends a %s decision to the exact quarantined batch",
    async (kind) => {
      mocks.POST.mockResolvedValue({ data: {} });
      const result = await resolveOperation(
        {},
        form({ kind, id: TASK, trip: TRIP, note: "Reviewed pings", confirmed: "on" }),
      );
      expect(mocks.POST).toHaveBeenCalledExactlyOnceWith(
        `/api/v1/admin/trips/{trip_id}/quarantined-batches/{quarantine_id}/${kind}`,
        {
          params: { path: { trip_id: TRIP, quarantine_id: TASK } },
          body: { note: "Reviewed pings" },
        },
      );
      expect(mocks.revalidatePath).toHaveBeenCalledWith("/admin/late-data");
      expect(result).toEqual({
        done: "Evidence decision recorded. Earnings and issued reports were not repriced or rewritten.",
      });
    },
  );

  it("surfaces the API's public error message", async () => {
    mocks.POST.mockRejectedValue(
      new ApiError(409, { code: "QUARANTINE_ALREADY_RESOLVED", message: "Already resolved." }),
    );
    expect(
      await resolveOperation(
        {},
        form({ kind: "discard", id: TASK, trip: TRIP, note: "Dupe", confirmed: "on" }),
      ),
    ).toEqual({ error: "Already resolved." });
    expect(mocks.revalidatePath).not.toHaveBeenCalled();
  });

  it("does not assume completion after a lost response", async () => {
    mocks.POST.mockRejectedValue(new TypeError("fetch failed: socket hang up"));
    expect(
      await resolveOperation(
        {},
        form({ kind: "contact", id: TASK, note: "Called", outcome: "failed", confirmed: "on" }),
      ),
    ).toEqual({ error: "No result was confirmed. Reload or retry the same action and note." });
  });
});
