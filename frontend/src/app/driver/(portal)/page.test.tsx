import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { watDay } from "@/lib/driver/daily-earnings";
import { frozenJob } from "@/lib/driver/frozen-job";
const mocks = vi.hoisted(() => ({
  earnings: vi.fn(),
  journey: vi.fn(),
  tracker: vi.fn(),
  visual: vi.fn(),
}));
vi.mock("@/lib/api/client", () => ({ createApiClient: () => ({ GET: mocks.visual }) }));
vi.mock("@/lib/auth/session", () => ({ getSessionToken: async () => "token" }));
vi.mock("@/lib/auth/current-user", () => ({
  requireRole: async () => ({ user: { id: "driver", full_name: "Ada Driver" } }),
}));
vi.mock("@/lib/driver/load-daily-earnings", () => ({ loadDailyEarnings: mocks.earnings }));
vi.mock("@/lib/driver/load-campaign-journey", () => ({ loadDriverCampaignJourney: mocks.journey }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
  redirect: (url: string) => {
    throw new Error(`redirect:${url}`);
  },
}));

vi.mock("./track/trip-tracker", () => ({
  TripTracker: (props: unknown) => {
    mocks.tracker(props);
    return <button>Start trip</button>;
  },
}));
import Home from "./page";
const assignment = {
  id: "job",
  campaignName: "Abuja launch",
  plateNumber: "ABC-123",
  vehicleId: "car",
};
const ready = {
  journey: { canStart: true, steps: [] },
  activationAssignment: assignment,
  trackerAssignment: assignment,
  currentTrip: null,
  photoStatus: "ready",
  visualAssignment: {
    id: "job",
    job: frozenJob({ zones: { target: [{ name: "Wuse II" }], exclusion: [] } }),
  },
};
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.setItem("cardvert-phone-intro:driver", "seen");
  mocks.earnings.mockResolvedValue({ state: "ready", data: [] });
  mocks.journey.mockResolvedValue(ready);
  mocks.visual.mockResolvedValue({
    data: {
      assignment: {
        id: "job",
        offer_terms: { zones: { target: [{ name: "Wuse II" }], exclusion: [] } },
      },
    },
  });
});
it("places the existing safe Start control under today's job and car", async () => {
  render(await Home());
  expect(screen.getByText("Abuja launch")).toBeVisible();
  expect(screen.getByText("Car ABC-123")).toBeVisible();
  expect(screen.getByRole("button", { name: "Start trip" })).toBeVisible();
  expect(mocks.tracker).toHaveBeenCalledWith(
    expect.objectContaining({ compact: true, assignment, driverId: "driver" }),
  );
  expect(screen.queryByText("Go to Start")).not.toBeInTheDocument();
});

it("adds only the matching authoritative job's frozen areas", async () => {
  render(await Home());
  expect(screen.getByText("Wuse II")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Start trip" })).toBeVisible();
});
it("never borrows areas from a different job or lets visual failure remove safe Start", async () => {
  mocks.journey.mockResolvedValue({
    ...ready,
    visualAssignment: {
      id: "different-job",
      job: frozenJob({ zones: { target: [{ name: "Wrong area" }] } }),
    },
  });
  render(await Home());
  expect(screen.queryByText("Wrong area")).toBeNull();
  expect(
    screen.getByText(/Your job areas couldn’t be loaded|Your job areas couldn't be loaded/),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Start trip" })).toBeVisible();
});
it("opens just the photo task when proof is due", async () => {
  mocks.journey.mockResolvedValue({ ...ready, photoStatus: "display_required" });
  render(await Home());
  expect(screen.getByRole("button", { name: "Take today’s photo" })).toBeVisible();
  expect(screen.queryByRole("button", { name: "Start trip" })).not.toBeInTheDocument();
});
it.each([
  ["Start trip", ready, "button"],
  ["Take today’s photo", { ...ready, photoStatus: "display_required" }, "button"],
  ["View live trip", { ...ready, currentTrip: { id: "trip" } }, "link"],
] as const)(
  "keeps %s when visual context is unavailable without making another active-job read",
  async (name, work, role) => {
    mocks.journey.mockResolvedValue({ ...work, visualAssignment: null });
    render(await Home());
    expect(screen.getByRole(role, { name })).toBeVisible();
    expect(screen.getByText(/Areas to avoid couldn't be loaded/)).toBeInTheDocument();
    expect(mocks.visual).not.toHaveBeenCalled();
  },
);
it("keeps an active trip on Track", async () => {
  mocks.journey.mockResolvedValue({ ...ready, currentTrip: { id: "trip" } });
  render(await Home());
  expect(screen.getByRole("link", { name: "View live trip" })).toHaveAttribute(
    "href",
    "/driver/track",
  );
  expect(mocks.tracker).not.toHaveBeenCalled();
});
it("shows only the blocking next step", async () => {
  mocks.journey.mockResolvedValue({
    ...ready,
    journey: {
      canStart: false,
      steps: [
        {
          state: "current",
          id: "person_payee",
          title: "Check your bank details",
          href: "/driver/profile",
        },
      ],
    },
  });
  render(await Home());
  expect(screen.getByRole("link", { name: "Check your bank details" })).toHaveAttribute(
    "href",
    "/driver/profile",
  );
  expect(screen.queryByText("Getting ready to drive")).not.toBeInTheDocument();
});
it.each([
  ["Here’s your current job.", ready],
  ["You’re on a trip now.", { ...ready, currentTrip: { id: "trip" } }],
  [
    "No job yet.",
    {
      ...ready,
      activationAssignment: null,
      journey: {
        canStart: false,
        steps: [
          { state: "current", id: "offer", title: "No current offer", href: "/driver/assignments" },
        ],
      },
    },
  ],
] as const)("leads with the factual heading %s, never a slogan", async (heading, work) => {
  mocks.journey.mockResolvedValue(work);
  render(await Home());
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(heading);
  expect(document.body).not.toHaveTextContent(/make today count/i);
});
it("fails closed for unavailable photo authority", async () => {
  mocks.journey.mockResolvedValue({ ...ready, photoStatus: "unavailable" });
  render(await Home());
  expect(screen.getByRole("link", { name: "Check photo status" })).toBeVisible();
  expect(mocks.tracker).not.toHaveBeenCalled();
});
it("shows compact pay without payment-operation copy or zero checks", async () => {
  mocks.earnings.mockResolvedValue({
    state: "ready",
    data: [
      {
        day: "2026-09-08",
        amount: "10000.00",
        currency: "NGN",
        status: "Paid 9 Sept",
        paidAt: "2026-09-09T01:00:00Z",
        tripIds: [],
      },
    ],
  });
  render(await Home());
  expect(screen.getByText(/Paid 9 Sept/)).toBeVisible();
  expect(
    screen.queryByText(/Ready to be paid|Still being checked|first payment|Paying tonight/i),
  ).not.toBeInTheDocument();
});
it("leads with the last actual payment when today's amount is zero", async () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-10T12:00:00Z"));
  try {
    mocks.earnings.mockResolvedValue({
      state: "ready",
      data: [
        {
          day: "2026-10-10",
          amount: "0.00",
          currency: "NGN",
          status: "Being checked",
          tripIds: [],
        },
        {
          day: "2026-10-08",
          amount: "10000.00",
          currency: "NGN",
          status: "Paid 9 Oct",
          paidAt: "2026-10-09T01:00:00Z",
          tripIds: [],
        },
      ],
    });
    render(await Home());
    expect(screen.getByText("Paid yesterday ₦10,000.00")).toBeVisible();
    expect(screen.queryByText(/Today ₦|Being checked/)).not.toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
});
it("orders payments by payment time rather than work day", async () => {
  mocks.earnings.mockResolvedValue({
    state: "ready",
    data: [
      {
        day: "2026-09-08",
        amount: "7000.00",
        currency: "NGN",
        status: "Paid 9 Sept",
        paidAt: "2026-09-09T01:00:00Z",
        tripIds: [],
      },
      {
        day: "2026-09-06",
        amount: "10000.00",
        currency: "NGN",
        status: "Paid 10 Sept",
        paidAt: "2026-09-10T01:00:00Z",
        tripIds: [],
      },
    ],
  });
  render(await Home());
  expect(screen.getByText("Paid 10 Sept ₦10,000.00")).toBeVisible();
  expect(screen.queryByText(/Today ₦/)).not.toBeInTheDocument();
});
it("shows an honest empty money state without a zero Today headline", async () => {
  render(await Home());
  expect(screen.getByText("No earnings yet")).toBeVisible();
  expect(screen.queryByText(/Today ₦/)).not.toBeInTheDocument();
});
it.each(["Being checked", "On hold – contact support", "Paying tonight"])(
  "shows a nonzero today's payment status: %s",
  async (status) => {
    mocks.earnings.mockResolvedValue({
      state: "ready",
      data: [{ day: watDay(new Date()), amount: "7143.00", currency: "NGN", status, tripIds: [] }],
    });
    render(await Home());
    expect(screen.getByText("Today ₦7,143.00")).toBeVisible();
    expect(screen.getByText(status)).toBeVisible();
  },
);
it("withholds money when complete history is unavailable", async () => {
  mocks.earnings.mockResolvedValue({ state: "unavailable" });
  render(await Home());
  expect(screen.getByRole("alert")).toHaveTextContent("Today’s earnings unavailable");
  expect(screen.queryByText(/Today ₦/)).not.toBeInTheDocument();
});
it("redirects an expired earnings session", async () => {
  mocks.earnings.mockResolvedValue({ state: "auth" });
  await expect(Home()).rejects.toThrow("redirect:/login");
});
