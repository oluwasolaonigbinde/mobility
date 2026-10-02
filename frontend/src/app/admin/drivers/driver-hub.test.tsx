import { render, screen, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  person: vi.fn(),
  vehicle: vi.fn(),
  carMenu: vi.fn(),
  setup: vi.fn(),
  driverMenu: vi.fn(),
  notFound: vi.fn(),
}));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.get }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("next/navigation", () => ({ notFound: mocks.notFound }));
vi.mock("../driver-applications/person-payee-decision-actions", () => ({
  PersonPayeeDecisionActions: (p: Record<string, unknown>) => {
    mocks.person(p);
    return <p>Audited documents</p>;
  },
}));
vi.mock("../driver-applications/vehicle-decision-actions", () => ({
  VehicleDecisionActions: (p: Record<string, unknown>) => {
    mocks.vehicle(p);
    return <p>Car documents</p>;
  },
}));
vi.mock("../driver-applications/account-setup-action", () => ({
  AccountSetupAction: (p: Record<string, unknown>) => {
    mocks.setup(p);
    return <p>Account setup</p>;
  },
}));
vi.mock("./onboarding-menu", () => ({
  DriverOnboardingMenu: (p: Record<string, unknown>) => {
    mocks.driverMenu(p);
    return <p>Driver controls</p>;
  },
}));
vi.mock("./details-form", () => ({ DriverDetailsForm: () => <p>Edit profile form</p> }));
vi.mock("../vehicles/vehicle-status-menu", () => ({
  VehicleStatusMenu: (p: Record<string, unknown>) => {
    mocks.carMenu(p);
    return <p>Car controls</p>;
  },
}));
vi.mock("../vehicles/new/vehicle-form", () => ({ VehicleForm: () => <p>Add car form</p> }));
vi.mock("../assignments/new/assignment-form", () => ({ AssignmentForm: () => <p>Offer form</p> }));
vi.mock("../assignments/cancel-button", () => ({
  CancelAssignmentButton: () => <button>Cancel job</button>,
}));
vi.mock("../assignments/activate-button", () => ({
  ActivateAssignmentButton: () => <button>Start job</button>,
}));
vi.mock("../payouts/process-trip-form", () => ({
  ProcessTripForm: ({ tripId }: { tripId: string }) => (
    <form>
      <input type="hidden" name="trip_session_id" value={tripId} />
      <button>Recalculate this trip</button>
    </form>
  ),
}));
vi.mock("../hub-drawer", () => ({
  HubDrawer: ({
    title,
    closeHref,
    children,
  }: {
    title: string;
    closeHref: string;
    children: React.ReactNode;
  }) => (
    <section aria-label={title}>
      <a href={closeHref}>Close</a>
      {children}
    </section>
  ),
}));
import DriverHub from "./driver-hub";
import { ApiError } from "@/lib/api/errors";
const driverId = "00000000-0000-4000-8000-000000000001";
const appId = "00000000-0000-4000-8000-000000000002";
const userId = "00000000-0000-4000-8000-000000000003";
const driver = {
  id: driverId,
  user_id: userId,
  full_name: "Ada Okafor",
  email: "ada@example.invalid",
  phone: "+2348039876543",
  service_city: "Abuja",
  onboarding_status: "pending",
};
const application = {
  id: appId,
  driver_profile_id: driverId,
  user_id: userId,
  full_name: driver.full_name,
  email: driver.email,
  status: "pending_review",
  person_payee: {
    status: "pending_review",
    submission_id: "person",
    bank_account_version_id: "bank",
    bank_account_verified: true,
    document_file_ids: { identity: "file" },
  },
  vehicle: {
    status: "pending_review",
    vehicle_id: "car",
    submission_id: "car-sub",
    document_file_ids: {},
  },
};
function reads({
  ready = false,
  accountStatus = "invited",
  app = application,
  failApplication = false,
}: {
  ready?: boolean;
  accountStatus?: string;
  app?: typeof application;
  failApplication?: boolean;
} = {}) {
  mocks.get.mockImplementation(async (path: string) => {
    if (path === "/api/v1/admin/drivers/{driver_profile_id}") return { data: driver };
    if (path === "/api/v1/admin/driver-applications/{application_id}") return { data: app };
    if (path === "/api/v1/admin/driver-applications") {
      if (failApplication) throw new Error("offline");
      return { data: { items: [app], total: 1 } };
    }
    if (path.endsWith("/users"))
      return { data: { items: [{ id: userId, status: accountStatus }], total: 1 } };
    if (path.endsWith("/vehicles"))
      return {
        data: { items: [{ id: "car", plate_number: "ABC-123-XY", status: "pending" }], total: 1 },
      };
    if (path.endsWith("/campaign-assignments"))
      return {
        data: {
          items: [
            {
              id: "job",
              campaign_id: "campaign",
              status: "accepted",
              campaign: { name: "PalmPay Wuse" },
              vehicle: { plate_number: "ABC-123-XY" },
              offered_at: "2026-09-28T10:00:00Z",
            },
          ],
          total: 1,
        },
      };
    if (path.endsWith("/readiness")) return { data: { ready, message: "Check funding" } };
    if (path.endsWith("/payout-calculations"))
      return {
        data: {
          items: [
            {
              id: "calc",
              trip_session_id: "trip",
              driver_profile_id: driverId,
              campaign_id: "campaign",
              calculated_at: "2026-09-29T10:00:00Z",
              trip_started_at: "2026-09-28T09:00:00Z",
              campaign_name: "PalmPay Wuse",
              final_payout: "7142.86",
              currency: "NGN",
              ledger_entry: { status: "pending" },
            },
          ],
          total: 1,
        },
      };
    if (path.includes("/debt-balances/"))
      return {
        data: {
          currency: "NGN",
          batch_payable: "7000.00",
          cash_paid: "10000.00",
          carry_forward_debt: "0.00",
        },
      };
    return { data: { items: [], total: 0 } };
  });
}
beforeEach(() => {
  vi.clearAllMocks();
  mocks.notFound.mockImplementation(() => {
    throw new Error("not found");
  });
  reads();
});
it("keeps exact audited document identities and blocks generic activation for a public applicant", async () => {
  render(await DriverHub({ driverId }));
  expect(screen.getByRole("heading", { name: "Ada Okafor" })).toBeTruthy();
  expect(mocks.person).toHaveBeenCalledWith({
    applicationId: appId,
    submissionId: "person",
    bankAccountVersionId: "bank",
    bankAccountVerified: true,
    documentFileIds: { identity: "file" },
    status: "pending_review",
  });
  expect(mocks.vehicle).toHaveBeenCalledWith(
    expect.objectContaining({ applicationId: appId, vehicleId: "car", submissionId: "car-sub" }),
  );
  expect(mocks.driverMenu).toHaveBeenCalledWith(
    expect.objectContaining({ activationBlocked: true }),
  );
  expect(mocks.setup).not.toHaveBeenCalled();
  expect(screen.queryByText(/NIN.*8901/)).toBeNull();
  expect(screen.queryByText("Phone verified")).toBeNull();
  expect(screen.queryByText("Terms accepted")).toBeNull();
  expect(screen.queryByText(/in this view/)).toBeNull();
  expect(screen.queryByText(/Transfer confirmation is separate/)).toBeNull();
  expect(screen.queryByText(/Recent trip pay calculations/)).toBeNull();
});

it.each(["approved", "pending_review"])(
  "keeps generic activation blocked for any linked public application (%s)",
  async (status) => {
    reads({ app: { ...application, status } });
    render(await DriverHub({ driverId }));
    expect(mocks.driverMenu).toHaveBeenCalledWith(
      expect.objectContaining({ activationBlocked: true }),
    );
  },
);
it("allows the existing activation action after a successful scoped read confirms no application", async () => {
  const original = mocks.get.getMockImplementation()!;
  mocks.get.mockImplementation(async (path, options) =>
    path.endsWith("/driver-applications")
      ? { data: { items: [], total: 0 } }
      : original(path, options),
  );
  render(await DriverHub({ driverId }));
  expect(mocks.driverMenu).toHaveBeenCalledWith(
    expect.objectContaining({ activationBlocked: false }),
  );
});
it("uses identity-scoped complaint and contact reads and opens their exact Support selection", async () => {
  const original = mocks.get.getMockImplementation()!;
  mocks.get.mockImplementation(async (path, options) => {
    if (path.endsWith("/complaints"))
      return {
        data: {
          items: [{ id: "complaint", status: "open", created_at: "2026-09-29T10:00:00Z" }],
          total: 1,
        },
      };
    if (path.endsWith("/manual-driver-contact-tasks"))
      return {
        data: {
          items: [{ id: "task", status: "completed", created_at: "2026-09-29T10:00:00Z" }],
          total: 1,
        },
      };
    return original(path, options);
  });
  render(await DriverHub({ driverId, query: { complaints_offset: "25", contacts_offset: "50" } }));
  expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/complaints", {
    params: { query: { user_id: userId, limit: 25, offset: 25 } },
  });
  expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/manual-driver-contact-tasks", {
    params: { query: { driver_profile_id: driverId, history: true, limit: 25, offset: 50 } },
  });
  expect(screen.getByRole("link", { name: /Needs a reply/ })).toHaveAttribute(
    "href",
    `/admin/support?tab=complaints&user_id=${userId}&complaint=complaint`,
  );
  expect(screen.getByRole("link", { name: /Completed/ })).toHaveAttribute(
    "href",
    `/admin/support?tab=contact&driver_profile_id=${driverId}&task=task`,
  );
});
it.each(["invited", "active"])(
  "account setup is available only for an approved invited account (%s)",
  async (status) => {
    reads({ accountStatus: status, app: { ...application, status: "approved" } });
    render(await DriverHub({ driverId }));
    if (status === "invited")
      expect(mocks.setup).toHaveBeenCalledWith({
        applicationId: appId,
        applicantName: driver.full_name,
      });
    else expect(mocks.setup).not.toHaveBeenCalled();
  },
);
it("does not link another person's documents even when their email matches", async () => {
  reads({ app: { ...application, user_id: "other-user" } });
  render(await DriverHub({ driverId, query: { application: appId } }));
  expect(mocks.person).not.toHaveBeenCalled();
  expect(mocks.vehicle).not.toHaveBeenCalled();
});
it("links accepted jobs to the campaign drawer without claiming readiness or offering Start", async () => {
  render(await DriverHub({ driverId }));
  expect(screen.queryByRole("button", { name: "Start job" })).toBeNull();
  expect(screen.getByRole("link", { name: "PalmPay Wuse" })).toHaveAttribute(
    "href",
    "/admin/campaigns/campaign?job=job#drivers",
  );
  expect(mocks.get.mock.calls.some(([path]) => path.endsWith("/readiness"))).toBe(false);
});
it("labels calculation dates accurately and recalculates only the selected trip without an ID field", async () => {
  render(await DriverHub({ driverId, query: { trip: "trip", jobs_offset: "25" } }));
  expect(screen.getByText(/Calculated/)).toBeTruthy();
  expect(screen.getByRole("navigation", { name: "Pay currency" })).toBeTruthy();
  expect(screen.queryByLabelText("Trip ID")).toBeNull();
  expect(document.querySelector('input[name="trip_session_id"]')).toHaveValue("trip");
  expect(screen.getByRole("link", { name: "Close" })).toHaveAttribute(
    "href",
    "/admin/drivers/" + driverId + "?jobs_offset=25#trips-and-pay",
  );
});
it("keeps failed document reads unavailable and activation blocked", async () => {
  reads({ failApplication: true });
  render(await DriverHub({ driverId }));
  expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load this section — try again");
  expect(screen.queryByText("No current identity submission is linked to this driver.")).toBeNull();
  expect(mocks.driverMenu).toHaveBeenCalledWith(
    expect.objectContaining({ activationBlocked: true }),
  );
  expect(mocks.carMenu).toHaveBeenCalledWith(expect.objectContaining({ activationBlocked: true }));
});
it.each([1, 25])("bounds cold hub reads independently of row count (%s)", async (size) => {
  const original = mocks.get.getMockImplementation()!;
  mocks.get.mockImplementation(async (path, options) => {
    const result = await original(path, options);
    if (path.endsWith("/payout-calculations") || path.endsWith("/campaign-assignments")) {
      result.data.items = Array.from({ length: size }, (_, i) => ({
        ...result.data.items[0],
        id: String(i),
      }));
      result.data.total = size;
    }
    return result;
  });
  render(
    await DriverHub({
      driverId,
      query: { trips_offset: "25", jobs_offset: "25", currency: "NGN" },
    }),
  );
  expect(mocks.get).toHaveBeenCalledTimes(11);
  expect(mocks.get).toHaveBeenCalledWith("/api/v1/admin/driver-applications", {
    params: { query: { driver_profile_id: driverId, user_id: userId, history: true, limit: 1 } },
  });
  expect(
    mocks.get.mock.calls.some(
      ([path]) =>
        path.endsWith("/analytics") ||
        path.endsWith("/campaigns/{campaign_id}") ||
        path.endsWith("/readiness"),
    ),
  ).toBe(false);
  expect(screen.getAllByText(/Trip date/)[0]).toHaveTextContent("PalmPay Wuse");
});
it("does not render a denied driver or fan out secondary reads", async () => {
  mocks.get.mockRejectedValue(new ApiError(403, { code: "DENIED", message: "Unavailable" }));
  await expect(DriverHub({ driverId })).rejects.toThrow("not found");
  expect(mocks.get).toHaveBeenCalledOnce();
});
it("uses the same sections for an applicant without a driver profile", async () => {
  const candidate = { ...application, driver_profile_id: null };
  mocks.get.mockImplementation(async (path) => {
    if (path.endsWith("/driver-applications/{application_id}")) return { data: candidate };
    return { data: { items: [], total: 0 } };
  });
  render(await DriverHub({ applicationId: appId }));
  expect(screen.getByRole("heading", { name: "Ada Okafor" })).toBeTruthy();
  expect(screen.getByRole("navigation", { name: "Page sections" })).toHaveTextContent(
    "Trips and pay",
  );
  expect(mocks.get.mock.calls.some(([path]) => path.endsWith("/audit-events"))).toBe(false);
  expect(mocks.driverMenu).not.toHaveBeenCalled();
  expect(mocks.get).not.toHaveBeenCalledWith(
    "/api/v1/admin/drivers/{driver_profile_id}",
    expect.anything(),
  );
});
it("keeps failed secondary reads unavailable instead of claiming empty records or zero pay", async () => {
  mocks.get.mockImplementation(async (path) => {
    if (path.endsWith("/drivers/{driver_profile_id}")) return { data: driver };
    throw new Error("offline");
  });
  render(await DriverHub({ driverId, query: { trip: "wrong-trip" } }));
  expect(screen.getAllByRole("alert").length).toBeGreaterThan(3);
  expect(screen.queryByText("No calculated trip pay recorded.")).toBeNull();
  expect(screen.queryByText("No activity recorded for this driver.")).toBeNull();
  expect(screen.queryByText("₦0.00")).toBeNull();
  for (const sectionId of [
    "details",
    "documents",
    "cars",
    "phone",
    "jobs",
    "trips-and-pay",
    "reviews",
    "activity",
  ]) {
    const section = document.getElementById(sectionId)!;
    expect(within(section).getAllByRole("alert")).toHaveLength(1);
    expect(within(section).getByRole("alert")).toHaveTextContent(
      "Couldn't load this section — try again",
    );
  }
  expect(
    screen.queryByText(
      /Account status unavailable|Trip date unavailable|Campaign unavailable|Account totals unavailable/,
    ),
  ).toBeNull();
});
it("shows driver's own reviews and activity and preserves each page's filters", async () => {
  const normal = mocks.get.getMockImplementation()!;
  mocks.get.mockImplementation(async (path, options) => {
    if (path.endsWith("/audit-events"))
      return {
        data: {
          items: [
            {
              id: "event",
              action: "admin.driver_profile.updated",
              actor_email: "staff@example.invalid",
              created_at: "2026-09-29T10:00:00Z",
            },
          ],
          total: 60,
        },
      };
    if (path.endsWith("/fraud-flags"))
      return {
        data: {
          items: [
            {
              id: "review",
              description: "Unusual trip speed",
              status: "open",
              created_at: "2026-09-29T10:00:00Z",
            },
          ],
          total: 60,
        },
      };
    return normal(path, options);
  });
  render(await DriverHub({ driverId, query: { reviews_offset: "25", activity_offset: "25" } }));
  expect(screen.getByRole("link", { name: /Unusual trip speed/ })).toHaveAttribute(
    "href",
    `/admin/trip-checks?tab=suspicious&driver_profile_id=${driverId}&flag=review`,
  );
  expect(screen.getByText(/Driver details or status updated/)).toHaveTextContent(
    "staff@example.invalid",
  );
  const next = screen.getAllByRole("link", { name: "Next →" });
  expect(next.some((link) => link.getAttribute("href")?.includes("reviews_offset=50"))).toBe(true);
  expect(next.some((link) => link.getAttribute("href")?.includes("activity_offset=50"))).toBe(true);
});

it("labels actual job lifecycle dates", async () => {
  reads();
  const normal = mocks.get.getMockImplementation()!;
  mocks.get.mockImplementation(async (path, options) => {
    const response = await normal(path, options);
    if (path.endsWith("/campaign-assignments"))
      response.data.items[0] = {
        ...response.data.items[0],
        activated_at: "2026-09-29T10:00:00Z",
        deactivated_at: "2026-09-30T10:00:00Z",
        cancelled_at: "2026-10-01T10:00:00Z",
      };
    return response;
  });
  render(await DriverHub({ driverId }));
  expect(screen.getByText(/^Started /)).toBeTruthy();
  expect(screen.getByText(/^Stopped /)).toBeTruthy();
  expect(screen.getByText(/^Cancelled /)).toBeTruthy();
});

it.each([false, true])(
  "bounds a selected application query even when candidate lookup fails (%s)",
  async (failCandidate) => {
    const normal = mocks.get.getMockImplementation()!;
    mocks.get.mockImplementation(async (path, options) => {
      if (failCandidate && path.endsWith("/driver-applications/{application_id}"))
        throw new Error("offline");
      return normal(path, options);
    });
    render(
      await DriverHub({ driverId, query: { application: appId, trip: "trip", currency: "NGN" } }),
    );
    expect(mocks.get).toHaveBeenCalledTimes(failCandidate ? 12 : 11);
    expect(
      mocks.get.mock.calls.some(
        ([path]) => path.endsWith("/readiness") || path.endsWith("/analytics"),
      ),
    ).toBe(false);
  },
);

it("uses actual active staff-added driver and car states without inventing document approval", async () => {
  const original = mocks.get.getMockImplementation()!;
  mocks.get.mockImplementation(async (path, options) => {
    if (path.endsWith("/drivers/{driver_profile_id}"))
      return { data: { ...driver, onboarding_status: "active" } };
    if (path.endsWith("/driver-applications")) return { data: { items: [], total: 0 } };
    if (path.endsWith("/vehicles"))
      return {
        data: {
          items: [
            { id: "car", status: "active", plate_number: "ABJ-101", driver_profile_id: driverId },
          ],
          total: 1,
        },
      };
    return original(path, options);
  });
  render(await DriverHub({ driverId }));
  expect(screen.getByText("Added by staff")).toBeVisible();
  expect(screen.queryByText("Next: review identity documents and bank details.")).toBeNull();
  expect(screen.queryByText("Identity documents")).toBeNull();
  expect(screen.getByText("Active car recorded")).toBeVisible();
});
