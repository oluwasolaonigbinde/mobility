import { expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
const patch = vi.hoisted(() => vi.fn());
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("@/lib/auth/current-user", () => ({ requireRole: vi.fn() }));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ PATCH: patch }) }));
import { updateVehicleStatusAction } from "./fleet-actions";
it("gives only staff actions the vehicle document review instructions", async () => {
  patch.mockRejectedValue(
    new ApiError(409, { code: "VEHICLE_APPROVAL_REQUIRED", message: "raw internal detail" }),
  );
  expect(
    await updateVehicleStatusAction({
      vehicleId: "10000000-0000-4000-8000-000000000001",
      status: "active",
    }),
  ).toEqual({
    error:
      "Use the car document review to approve this car. For an expired approval, changed car details or rejected documents, ask the driver for a fresh submission from Profile.",
  });
});
