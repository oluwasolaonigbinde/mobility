import { describe, expect, it } from "vitest";
import { tokenNeedsRefresh } from "./token";

function token(exp: number): string {
  const payload = btoa(JSON.stringify({ exp }))
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
  return `header.${payload}.signature`;
}

describe("tokenNeedsRefresh", () => {
  it("refreshes inside the threshold", () => {
    expect(tokenNeedsRefresh(token(1_500), 600, 1_000)).toBe(true);
  });

  it("does not refresh a fresh token", () => {
    expect(tokenNeedsRefresh(token(2_000), 600, 1_000)).toBe(false);
  });

  it("fails closed for malformed token timing", () => {
    expect(tokenNeedsRefresh("not-a-token", 600, 1_000)).toBe(false);
  });
});
