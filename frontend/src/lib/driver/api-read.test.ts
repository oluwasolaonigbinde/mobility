import { expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

vi.mock("server-only", () => ({}));
import { readDriverApi } from "./api-read";

it("explains the duplicate-job conflict without exposing backend details", async () => {
  expect(
    await readDriverApi(async () => {
      throw new ApiError(409, { code: "MULTIPLE_ACTIVE_ASSIGNMENTS", message: "Internal detail" });
    }),
  ).toEqual({
    state: "unavailable",
    message: "Two jobs are live on your account. Please contact support so we can fix it.",
  });
});

it.each([
  [401, "MULTIPLE_ACTIVE_ASSIGNMENTS", { state: "auth" }],
  [403, "FORBIDDEN", { state: "auth" }],
  [404, "NOT_FOUND", { state: "missing" }],
  [409, "OTHER_CONFLICT", { state: "unavailable" }],
  [503, "UNAVAILABLE", { state: "unavailable" }],
] as const)("preserves other error handling: %s %s", async (status, code, expected) => {
  expect(
    await readDriverApi(
      async () => {
        throw new ApiError(status, { code, message: "Internal detail" });
      },
      { notFoundIsMissing: true },
    ),
  ).toEqual(expected);
});
