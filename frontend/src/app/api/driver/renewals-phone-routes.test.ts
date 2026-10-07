import { beforeEach, expect, it, vi } from "vitest";
import { GET as contact } from "./contact/route";
import { PUT as phone } from "./contact/phone/route";
import { POST as issue } from "./contact/phone-verification/route";
import { GET as documents } from "./documents/route";
import { POST as renew } from "./documents/person-payee/route";
import { POST as vehicle } from "./vehicles/[vehicleId]/documents/route";
import { ApiError } from "@/lib/api/errors";
const mocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn(), token: vi.fn() }));
vi.mock("@/lib/api/client", () => ({
  createApiClient: (token: unknown) => {
    mocks.token(token);
    return { GET: mocks.get, PUT: mocks.put, POST: mocks.post };
  },
}));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "signed-in-cookie" }));
beforeEach(() => {
  vi.clearAllMocks();
  for (const fn of [mocks.get, mocks.put, mocks.post])
    fn.mockResolvedValue({ data: { status: "pending" } });
});
function request(body: unknown) {
  return new Request("http://localhost/api/driver/documents", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}
it("uses signed-in authority and no-store for driver reads and sole code response", async () => {
  for (const action of [contact, documents]) {
    const r = await action();
    expect(r.headers.get("cache-control")).toBe("no-store");
    expect(r.status).toBe(200);
  }
  mocks.post.mockResolvedValue({ data: { code: "485921", terrax_number: "+447700900999" } });
  const r = await issue();
  expect(await r.json()).toEqual({ code: "485921", terrax_number: "+447700900999" });
  expect(r.headers.get("cache-control")).toBe("no-store");
  expect(mocks.token).toHaveBeenCalledWith("signed-in-cookie");
});
it("forwards current revision IDs and upload references to owned routes", async () => {
  const body = {
    expected_submission_id: "current",
    client_request_id: "retry",
    registration_file_id: "file",
  };
  await phone(request({ phone: "+447700900101" }));
  await renew(request(body));
  await vehicle(request(body), { params: Promise.resolve({ vehicleId: "owned-vehicle" }) });
  expect(mocks.put).toHaveBeenCalledWith("/api/v1/driver/contact/phone", {
    body: { phone: "+447700900101" },
  });
  expect(mocks.post).toHaveBeenCalledWith("/api/v1/driver/documents/person-payee", { body });
  expect(mocks.post).toHaveBeenCalledWith(
    "/api/v1/driver/vehicles/{vehicle_id}/evidence-submissions",
    { params: { path: { vehicle_id: "owned-vehicle" } }, body },
  );
});
it("keeps safe rejection errors free from driver code and token", async () => {
  mocks.post.mockRejectedValue(
    new ApiError(403, { code: "FORBIDDEN_ROLE", message: "Driver role is required" }),
  );
  const response = await issue();
  expect(response.status).toBe(403);
  expect(await response.text()).not.toContain("485921");
});
it("rejects malformed sensitive JSON without echoing it or calling the backend", async () => {
  for (const action of [
    phone,
    renew,
    (r: Request) => vehicle(r, { params: Promise.resolve({ vehicleId: "v" }) }),
  ]) {
    const response = await action(
      new Request("http://localhost", { method: "POST", body: '{"nin":"485921"' }),
    );
    expect(response.status).toBe(400);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.text()).not.toContain("485921");
  }
  expect(mocks.post).not.toHaveBeenCalled();
  expect(mocks.put).not.toHaveBeenCalled();
});
