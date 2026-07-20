import { describe, expect, it } from "vitest";
import { loginClientIpHeader } from "./client-ip";

describe("loginClientIpHeader", () => {
  it("does not relay a browser-supplied header by default", () => {
    const headers = new Headers({ "X-Client-IP": "198.51.100.8" });
    expect(loginClientIpHeader(headers, false)).toBeUndefined();
  });

  it("relays the edge-created header only after explicit opt-in", () => {
    const headers = new Headers({ "X-Client-IP": "198.51.100.8" });
    expect(loginClientIpHeader(headers, true)).toBe("198.51.100.8");
  });
});
