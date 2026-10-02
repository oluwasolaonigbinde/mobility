import { beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  patch: vi.fn(),
  get: vi.fn(),
  redirect: vi.fn(),
}));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: mocks.redirect }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("@/lib/api/client", () => ({
  createApiClient: () => ({ POST: mocks.post, PATCH: mocks.patch, GET: mocks.get }),
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

const createdUserId = "00000000-0000-4000-8000-00000000000a";
const retryState = {
  createdUserId,
  createdEmail: "new@example.com",
  createdFullName: "New User",
  createdPhone: null,
};
function companyForm() {
  const data = form("advertiser");
  data.set("org_name", "Example company");
  return data;
}
it("requires a company name before creating its advertiser login", async () => {
  expect(await createUserAction({}, form("advertiser"))).toEqual({
    error: "Company name is required",
  });
  expect(mocks.post).not.toHaveBeenCalled();
});
it("retains the created login after company creation fails without retaining its password", async () => {
  mocks.post
    .mockResolvedValueOnce({ data: { id: createdUserId } })
    .mockRejectedValueOnce(new Error("offline"));
  const result = await createUserAction({}, companyForm());
  expect(result).toEqual({
    ...retryState,
    error: expect.stringContaining("Retry the company below"),
  });
  expect(result).not.toHaveProperty("password");
});
it("retries only the company after checking the actual existing advertiser identity", async () => {
  mocks.get.mockResolvedValue({
    data: {
      items: [
        {
          id: createdUserId,
          role: "advertiser",
          email: retryState.createdEmail,
          full_name: retryState.createdFullName,
        },
      ],
      total: 1,
    },
  });
  mocks.post.mockResolvedValue({ data: { organization: { id: "company-id" } } });
  const data = companyForm();
  data.delete("password");
  await createUserAction(retryState, data);
  expect(mocks.get).toHaveBeenCalledExactlyOnceWith("/api/v1/admin/users", {
    params: { query: { role: "advertiser", q: retryState.createdEmail, limit: 100, offset: 0 } },
  });
  expect(mocks.post).toHaveBeenCalledExactlyOnceWith("/api/v1/admin/advertiser-organizations", {
    body: {
      name: "Example company",
      currency: "NGN",
      owner_user_id: createdUserId,
      status: "active",
    },
  });
  expect(mocks.redirect).toHaveBeenCalledWith("/admin/advertisers/company-id");
});
it.each(["role", "email", "full_name"])(
  "refuses a changed existing %s before retrying the company",
  async (key) => {
    mocks.get.mockResolvedValue({
      data: {
        items: [
          {
            id: createdUserId,
            role: "advertiser",
            email: retryState.createdEmail,
            full_name: retryState.createdFullName,
            [key]: "changed",
          },
        ],
        total: 1,
      },
    });
    expect((await createUserAction(retryState, companyForm())).error).toContain("does not match");
    expect(mocks.post).not.toHaveBeenCalled();
  },
);
it("finds the exact created login after a full first page without selecting a similar account", async () => {
  mocks.get
    .mockResolvedValueOnce({
      data: {
        items: Array.from({ length: 100 }, (_, i) => ({
          id: `similar-${i}`,
          role: "advertiser",
          email: retryState.createdEmail,
          full_name: retryState.createdFullName,
        })),
        total: 101,
      },
    })
    .mockResolvedValueOnce({
      data: {
        items: [
          {
            id: createdUserId,
            role: "advertiser",
            email: retryState.createdEmail,
            full_name: retryState.createdFullName,
          },
        ],
        total: 101,
      },
    });
  mocks.post.mockResolvedValue({ data: { organization: { id: "company-id" } } });
  await createUserAction(retryState, companyForm());
  expect(mocks.get).toHaveBeenNthCalledWith(2, "/api/v1/admin/users", {
    params: { query: { role: "advertiser", q: retryState.createdEmail, limit: 100, offset: 100 } },
  });
  expect(mocks.post).toHaveBeenCalledOnce();
  expect(mocks.post.mock.calls[0]![1].body.owner_user_id).toBe(createdUserId);
});
it("refuses an incomplete retry page without creating another login", async () => {
  mocks.get.mockResolvedValue({ data: { items: [], total: 101 } });
  expect((await createUserAction(retryState, companyForm())).error).toContain("does not match");
  expect(mocks.post).not.toHaveBeenCalled();
});
it("refuses a malformed retry identity and preserves a valid retry through validation and read errors", async () => {
  expect(
    (await createUserAction({ ...retryState, createdUserId: "invalid" }, companyForm())).error,
  ).toContain("does not match");
  expect(mocks.get).not.toHaveBeenCalled();
  const data = companyForm();
  data.set("org_name", "");
  expect(await createUserAction(retryState, data)).toEqual({
    ...retryState,
    error: "Company name is required",
  });
  mocks.get.mockRejectedValue(new Error("offline"));
  expect(await createUserAction(retryState, companyForm())).toEqual({
    ...retryState,
    error: "Could not reach the server.",
  });
  expect(mocks.post).not.toHaveBeenCalled();
});

it.each(["", undefined])(
  "rejects an incomplete retry id (%s) without creating a login",
  async (createdUserId) => {
    expect(
      (await createUserAction({ ...retryState, createdUserId }, companyForm())).error,
    ).toContain("does not match");
    expect(mocks.post).not.toHaveBeenCalled();
  },
);
it("keeps the existing login retry state when company confirmation is empty", async () => {
  mocks.post
    .mockResolvedValueOnce({ data: { id: createdUserId } })
    .mockResolvedValueOnce({ data: undefined });
  expect(await createUserAction({}, companyForm())).toEqual({
    ...retryState,
    error: expect.stringContaining("Retry the company below"),
  });
  expect(mocks.redirect).not.toHaveBeenCalled();
});
