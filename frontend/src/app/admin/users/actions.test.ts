import { beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ post: vi.fn(), patch: vi.fn() }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: vi.fn() }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("@/lib/api/client", () => ({
  createApiClient: () => ({ POST: mocks.post, PATCH: mocks.patch }),
}));
import { createUserAction, updateUserStatusAction } from "./actions";

beforeEach(() => {
  vi.clearAllMocks();
  mocks.post.mockResolvedValue({ data: { id: "new-user" } });
  mocks.patch.mockResolvedValue({});
});

function form(role = "admin", proof?: string) {
  const data = new FormData();
  for (const [key, value] of Object.entries({
    email: "new@example.com",
    full_name: "New User",
    role,
    password: "new-user-password",
  }))
    data.set(key, value);
  if (proof !== undefined) data.set("current_password", proof);
  return data;
}

it("requires the acting administrator's password before creating an administrator", async () => {
  expect(await createUserAction({}, form())).toEqual({
    error: "Your current password is required",
  });
  expect(mocks.post).not.toHaveBeenCalled();
});

it("forwards the exact proof only for administrator creation", async () => {
  await createUserAction({}, form("admin", " proof with spaces "));
  expect(mocks.post).toHaveBeenLastCalledWith("/api/v1/admin/users", {
    body: expect.objectContaining({ role: "admin", current_password: " proof with spaces " }),
  });
  await createUserAction({}, form("driver", "unneeded-secret"));
  expect(mocks.post.mock.calls.at(-1)?.[1].body).not.toHaveProperty("current_password");
});

it("forwards reactivation proof without putting it in returned state", async () => {
  const result = await updateUserStatusAction({
    userId: "00000000-0000-4000-8000-00000000000a",
    status: "active",
    current_password: " proof with spaces ",
  });
  expect(mocks.patch).toHaveBeenCalledWith("/api/v1/admin/users/{user_id}", {
    params: { path: { user_id: "00000000-0000-4000-8000-00000000000a" } },
    body: { status: "active", current_password: " proof with spaces " },
  });
  expect(result).toEqual({});
});
