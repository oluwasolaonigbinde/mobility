import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { PerformanceCard } from "./performance-card";
const data = {
  estimatedViews: "140",
  distance: "14000",
  cars: 3,
  viewChange: 100,
  distanceChange: -20,
  windowLabel: "Last 7 days",
  dailyMessage: null,
  days: [
    {
      date: "2026-11-14",
      estimated_impressions: "140",
      distance_m: "14000",
      status: "released" as const,
    },
  ],
};
it.each([true, false])(
  "shows estimates distance cars and accessible daily chart, compact %s",
  (compact) => {
    const { container } = render(<PerformanceCard {...data} compact={compact} />);
    expect(screen.getByText("Estimated views")).toBeVisible();
    expect(screen.getByText("14 km")).toBeVisible();
    expect(screen.getByText("↑ 100%")).toBeVisible();
    expect(screen.getByText("↓ 20%")).toBeVisible();
    expect(screen.getByText("About 15 minutes ago")).toBeVisible();
    expect(screen.getByText("An estimate, not a count of people")).toBeVisible();
    expect(screen.getByText("Daily figures")).toBeInTheDocument();
    expect(container.querySelector("svg polygon")).not.toBeNull();
    expect(screen.queryByText("QR scans")).toBeNull();
  },
);
it("replaces chart for unreleased days", () => {
  render(
    <PerformanceCard
      {...data}
      days={null}
      estimatedViews={null}
      distance={null}
      dailyMessage="Not enough cars yet to show daily figures."
      windowLabel="Last 7 days"
      viewChange={null}
      distanceChange={null}
    />,
  );
  expect(screen.getByText("Last 7 days")).toBeVisible();
  expect(screen.queryByRole("img")).toBeNull();
  expect(screen.getByText("Not enough cars yet to show daily figures.")).toBeVisible();
});

it.each([true, false])(
  "uses rounded gridlines, seven dots and seven readable dates (compact %s)",
  (compact) => {
    const days = Array.from({ length: 7 }, (_, i) => ({
      date: `2026-11-${String(i + 2).padStart(2, "0")}`,
      estimated_impressions: String(80000 + i * 10000),
      distance_m: "1000",
      status: "released" as const,
    }));
    const { container } = render(<PerformanceCard {...data} days={days} compact={compact} />);
    const chart = screen.getByRole("img", { name: "Estimated views per day; daily figures below" });
    expect(chart).toHaveTextContent("0");
    expect(chart).toHaveTextContent("50k");
    expect(chart).toHaveTextContent("100k");
    expect(chart).toHaveTextContent("150k");
    expect(chart.querySelectorAll("svg line")).toHaveLength(4);
    expect(chart.querySelectorAll("span[aria-hidden=true]")).toHaveLength(7);
    expect(chart.querySelectorAll("time")).toHaveLength(7);
    expect([...chart.querySelectorAll("time")].map((t) => t.textContent)).toEqual([
      "2 Nov",
      "3",
      "4",
      "5",
      "6",
      "7",
      "8",
    ]);
    if (!compact)
      expect(container.querySelector("header")).toHaveTextContent(
        "Campaign performanceLast 7 days",
      );
  },
);
it.each(["Last 7 days", "Cancelled", "Final 7 days", "No results yet"])(
  "keeps %s in the full card heading slot",
  (windowLabel) => {
    const { container } = render(<PerformanceCard {...data} windowLabel={windowLabel} />);
    expect(container.querySelector("header")).toHaveTextContent(
      `Campaign performance${windowLabel}`,
    );
  },
);

it.each([true, false])("renders only dashes for every fallback, compact %s", async (compact) => {
  const { summarizePerformance } = await import("@/lib/advertiser/performance");
  const campaign = {
    start_at: "2026-11-01T00:00:00+01:00",
    end_at: "2026-11-14T23:00:00+01:00",
    status: "active",
  };
  const now = new Date("2026-11-15T12:00Z");
  const rows = Array.from({ length: 14 }, (_, i) => ({
    date: `2026-11-${String(i + 1).padStart(2, "0")}`,
    estimated_impressions: "1000",
    distance_m: "10000",
    status: "released" as const,
  }));
  for (const [status, days] of [
    [
      "active",
      rows.map((d, i) =>
        i === 13
          ? {
              ...d,
              status: "not_enough_cars" as const,
              estimated_impressions: null,
              distance_m: null,
            }
          : d,
      ),
    ],
    ["active", rows.map((d, i) => (i === 13 ? { ...d, estimated_impressions: null } : d))],
    ["active", null],
    ["finished", null],
    ["cancelled", rows],
  ] as const) {
    const result = summarizePerformance({ ...campaign, status }, days, now);
    const { container, unmount } = render(
      <PerformanceCard {...result} cars={3} compact={compact} />,
    );
    expect([...container.querySelectorAll("dd")].map((d) => d.textContent)).toEqual([
      "—",
      "—",
      "3",
    ]);
    expect(screen.queryByRole("img")).toBeNull();
    expect(container).not.toHaveTextContent(/%|So far|1,000|10 km/);
    expect(
      screen.getByText(
        status === "cancelled"
          ? "Cancelled"
          : status === "finished"
            ? "Final 7 days"
            : "Last 7 days",
      ),
    ).toBeVisible();
    unmount();
  }
});
