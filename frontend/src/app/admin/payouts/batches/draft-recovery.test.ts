import { describe, expect, it } from "vitest";
import { readDraftRecovery, retainDraftRecovery } from "./draft-recovery";

describe("durable payout recovery", () => {
  it("reuses the saved identity and exact selection across tabs and reloads", () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => {
        values.set(key, value);
      },
    };
    const first = retainDraftRecovery(storage, "maker", "NGN", [
      "22222222-2222-4222-8222-222222222222",
    ]);
    expect(readDraftRecovery(storage, "maker")).toEqual(first);
    expect(
      retainDraftRecovery(storage, "maker", "USD", ["33333333-3333-4333-8333-333333333333"]),
    ).toEqual(first);
    expect(readDraftRecovery(storage, "other-admin")).toBeNull();
  });

  it("fails before submission if durable storage is unavailable or malformed", () => {
    expect(() =>
      retainDraftRecovery(
        {
          getItem: () => null,
          setItem: () => {
            throw new Error("quota");
          },
        },
        "maker",
        "NGN",
        ["22222222-2222-4222-8222-222222222222"],
      ),
    ).toThrow();
    expect(() => readDraftRecovery({ getItem: () => "{}" }, "maker")).toThrow();
  });
});
