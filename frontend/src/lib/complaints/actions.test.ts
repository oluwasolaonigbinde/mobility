import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  patch: vi.fn(),
  revalidatePath: vi.fn(),
  redirect: vi.fn((url: string) => {
    throw new Error(`REDIRECT:${url}`);
  }),
}));

vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("next/navigation", () => ({ redirect: mocks.redirect }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: vi.fn(async () => "token") }));
vi.mock("@/lib/api/client", () => ({
  createApiClient: () => ({ POST: mocks.post, PATCH: mocks.patch }),
}));

import {
  followUpAdvertiserComplaintAction,
  followUpDriverComplaintAction,
  raiseAdvertiserComplaintAction,
  raiseDriverComplaintAction,
  replyToComplaintAction,
  updateComplaintAction,
} from "./actions";

const COMPLAINT = "00000000-0000-4000-8000-00000000000c";
const TRIP = "00000000-0000-4000-8000-00000000000d";
const REQUEST = "00000000-0000-4000-8000-00000000000e";
const STAFF = "00000000-0000-4000-8000-00000000000f";

function form(values: Record<string, string>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(values)) data.set(key, value);
  return data;
}

function apiError(status: number, code: string) {
  return new ApiError(status, { code, message: "server text" });
}

describe("raise complaint actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: { id: COMPLAINT } });
  });

  it("sends the chosen record and opens the new conversation", async () => {
    await expect(
      raiseDriverComplaintAction(
        {},
        form({
          category: "trip_or_tracking",
          message: "  The trip stopped recording.  ",
          reference: `trip:${TRIP}`,
          client_request_id: REQUEST,
        }),
      ),
    ).rejects.toThrow(`REDIRECT:/driver/help/${COMPLAINT}`);
    expect(mocks.post).toHaveBeenCalledWith("/api/v1/driver/complaints", {
      body: {
        category: "trip_or_tracking",
        message: "The trip stopped recording.",
        client_request_id: REQUEST,
        reference_type: "trip",
        reference_id: TRIP,
      },
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/driver/help");
  });

  it("omits the record when none is chosen (advertiser)", async () => {
    await expect(
      raiseAdvertiserComplaintAction(
        {},
        form({ category: "account", message: "Help", reference: "", client_request_id: REQUEST }),
      ),
    ).rejects.toThrow(`REDIRECT:/advertiser/help/${COMPLAINT}`);
    expect(mocks.post).toHaveBeenCalledWith("/api/v1/advertiser/complaints", {
      body: { category: "account", message: "Help", client_request_id: REQUEST },
    });
  });

  it("validates before calling the server", async () => {
    const base = { category: "account", message: "x", reference: "", client_request_id: REQUEST };
    expect(await raiseDriverComplaintAction({}, form({ ...base, category: "" }))).toEqual({
      error: "Choose what your complaint is about",
    });
    expect(await raiseDriverComplaintAction({}, form({ ...base, message: "   " }))).toEqual({
      error: "Write a message first",
    });
    expect(await raiseDriverComplaintAction({}, form({ ...base, reference: "trip:nope" }))).toEqual(
      { error: "Choose a record from the list" },
    );
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it.each([
    [
      apiError(404, "COMPLAINT_REFERENCE_NOT_FOUND"),
      "We couldn't find that record in your account. Choose another one or leave it out.",
    ],
    [
      apiError(404, "DRIVER_PROFILE_NOT_FOUND"),
      "Your account can't use Help right now. Sign in again, then try again.",
    ],
    [apiError(401, "INVALID_TOKEN"), "Your session has ended. Sign in again, then try again."],
    [
      apiError(409, "COMPLAINT_REPLAY_CONFLICT"),
      "This was already sent with different details. Refresh the page to see it.",
    ],
    [
      apiError(422, "COMPLAINT_CATEGORY_NOT_ALLOWED"),
      "Some details weren't accepted. Check them and try again.",
    ],
    [apiError(500, "INTERNAL"), "Cardvert couldn't send this right now. Try again in a moment."],
    [
      new Error("offline"),
      "Cardvert couldn't send this right now. Check your connection and try again.",
    ],
  ])("explains server refusals in plain words (%#)", async (error, message) => {
    mocks.post.mockRejectedValueOnce(error);
    expect(
      await raiseDriverComplaintAction(
        {},
        form({ category: "other", message: "Hi", reference: "", client_request_id: REQUEST }),
      ),
    ).toEqual({ error: message });
    expect(mocks.redirect).not.toHaveBeenCalled();
  });

  it("treats an empty success body as a failed send", async () => {
    mocks.post.mockResolvedValueOnce({});
    expect(
      await raiseDriverComplaintAction(
        {},
        form({ category: "other", message: "Hi", reference: "", client_request_id: REQUEST }),
      ),
    ).toEqual({
      error: "Cardvert couldn't send this right now. Check your connection and try again.",
    });
  });
});

describe("follow-up actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: {} });
  });

  it.each([
    ["driver", followUpDriverComplaintAction, "/api/v1/driver/complaints/{complaint_id}/messages"],
    [
      "advertiser",
      followUpAdvertiserComplaintAction,
      "/api/v1/advertiser/complaints/{complaint_id}/messages",
    ],
  ] as const)("adds a %s message and refreshes the thread", async (party, action, path) => {
    expect(
      await action(
        {},
        form({ complaint_id: COMPLAINT, message: "Any news?", client_request_id: REQUEST }),
      ),
    ).toEqual({ done: "Sent. Customer Service will reply here." });
    expect(mocks.post).toHaveBeenCalledWith(path, {
      params: { path: { complaint_id: COMPLAINT } },
      body: { message: "Any news?", client_request_id: REQUEST },
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith(`/${party}/help/${COMPLAINT}`);
  });

  it("explains a full conversation and a missing complaint", async () => {
    const values = { complaint_id: COMPLAINT, message: "x", client_request_id: REQUEST };
    mocks.post.mockRejectedValueOnce(apiError(409, "COMPLAINT_MESSAGE_LIMIT"));
    expect(await followUpDriverComplaintAction({}, form(values))).toEqual({
      error: "This conversation is full. Please raise a new complaint instead.",
    });
    mocks.post.mockRejectedValueOnce(apiError(404, "COMPLAINT_NOT_FOUND"));
    expect(await followUpDriverComplaintAction({}, form(values))).toEqual({
      error: "This complaint couldn't be found.",
    });
    mocks.post.mockRejectedValueOnce(apiError(404, "ADVERTISER_ORGANIZATION_NOT_FOUND"));
    expect(await followUpAdvertiserComplaintAction({}, form(values))).toEqual({
      error: "Your account can't use Help right now. Sign in again, then try again.",
    });
    expect(
      await followUpDriverComplaintAction({}, form({ ...values, complaint_id: "bad" })),
    ).toHaveProperty("error");
  });
});

describe("staff actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.post.mockResolvedValue({ data: {} });
    mocks.patch.mockResolvedValue({ data: {} });
  });

  it("replies, optionally resolving", async () => {
    const values = { complaint_id: COMPLAINT, message: "Fixed", client_request_id: REQUEST };
    expect(await replyToComplaintAction({}, form({ ...values, resolve: "on" }))).toEqual({
      done: "Reply sent and complaint resolved.",
    });
    expect(mocks.post).toHaveBeenCalledWith("/api/v1/admin/complaints/{complaint_id}/messages", {
      params: { path: { complaint_id: COMPLAINT } },
      body: { message: "Fixed", client_request_id: REQUEST, resolve: true },
    });
    expect(await replyToComplaintAction({}, form(values))).toEqual({ done: "Reply sent." });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/admin/support");
    mocks.post.mockRejectedValueOnce(apiError(404, "COMPLAINT_NOT_FOUND"));
    expect(await replyToComplaintAction({}, form(values))).toEqual({
      error: "This complaint couldn't be found.",
    });
    expect(await replyToComplaintAction({}, form({ ...values, message: "" }))).toEqual({
      error: "Write a message first",
    });
  });

  it.each([
    [{ status: "resolved", assignee: "" }, { status: "resolved" }],
    [{ status: "", assignee: "none" }, { assigned_to_user_id: null }],
    [
      { status: "open", assignee: STAFF },
      { status: "open", assigned_to_user_id: STAFF },
    ],
    [{ status: "", assignee: "" }, {}],
  ])("maps the status and assignment form %#", async (values, body) => {
    expect(await updateComplaintAction({}, form({ complaint_id: COMPLAINT, ...values }))).toEqual({
      done: "Saved.",
    });
    expect(mocks.patch).toHaveBeenCalledWith("/api/v1/admin/complaints/{complaint_id}", {
      params: { path: { complaint_id: COMPLAINT } },
      body,
    });
  });

  it("refuses bad input and explains an invalid assignee", async () => {
    expect(
      await updateComplaintAction(
        {},
        form({ complaint_id: COMPLAINT, status: "closed", assignee: "" }),
      ),
    ).toEqual({ error: "Choose a status or a staff member." });
    mocks.patch.mockRejectedValueOnce(apiError(422, "COMPLAINT_ASSIGNEE_INVALID"));
    expect(
      await updateComplaintAction(
        {},
        form({ complaint_id: COMPLAINT, status: "", assignee: STAFF }),
      ),
    ).toEqual({ error: "Choose an active Terrax Media staff member." });
  });
});
