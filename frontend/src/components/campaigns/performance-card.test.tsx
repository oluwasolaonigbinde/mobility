import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { PerformanceCard } from "./performance-card";

const data = {
  estimatedViews: "1200",
  cars: 1,
  scans: 2,
  days: [{ date: "2026-10-20", distance_m: "25000" }],
};
it("keeps Home's figures and chart compact without repeating the heading or period", () => {
  render(<PerformanceCard {...data} compact />);
  expect(screen.queryByRole("heading", { name: "Campaign performance" })).toBeNull();
  expect(screen.getByText("Estimated views")).toBeInTheDocument();
  expect(screen.getByText("As of about 15 minutes ago")).toBeInTheDocument();
  expect(screen.getByText("QR scans")).toBeInTheDocument();
  expect(screen.getByText("Daily figures")).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent(/UTC|couldn't|refresh/i);
});
it("explains privacy withholding without suggesting a refresh", () => {
  render(
    <PerformanceCard estimatedViews={null} cars={1} scans={0} days={null} withheld daysWithheld />,
  );
  expect(screen.getByText("Not enough cars yet to show estimated views.")).toBeInTheDocument();
  expect(screen.getByText("Not enough cars yet to show daily distance.")).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent(/refresh|couldn't|QR scans/i);
});
it("keeps a retry explanation for an operational failure", () => {
  render(<PerformanceCard {...data} unavailable />);
  expect(screen.getByRole("status")).toHaveTextContent("Refresh to try again");
  expect(document.body).not.toHaveTextContent("Not enough cars");
});

it("collapses withheld daily figures without presenting them as a zero chart", () => {
  render(
    <PerformanceCard
      estimatedViews="1200"
      cars={1}
      scans={0}
      daysWithheld
      days={[
        { date: "2026-10-19", distance_m: null },
        { date: "2026-10-20", distance_m: "0" },
        { date: "2026-10-21", distance_m: "25000" },
      ]}
    />,
  );
  expect(screen.getByText("Not enough cars yet to show daily distance.")).toBeInTheDocument();
  expect(screen.queryByRole("img", { name: /Daily distance chart/ })).toBeNull();
  expect(screen.queryByText("Daily figures")).toBeNull();
  expect(document.body).not.toHaveTextContent(/UTC|refresh|couldn't/i);
});

it("still shows genuine zero days when the API permits their figures", () => {
  render(
    <PerformanceCard
      estimatedViews="0"
      cars={0}
      scans={0}
      days={[{ date: "2026-10-21", distance_m: "0" }]}
    />,
  );
  expect(screen.getByRole("img", { name: /Daily distance chart/ })).toBeInTheDocument();
  expect(screen.getByText("0 km")).toBeInTheDocument();
  expect(screen.queryByText("Not enough cars yet to show daily distance.")).toBeNull();
});
it("shows no results yet instead of an inverted reporting window", () => {
  render(
    <PerformanceCard
      {...data}
      period={{ start_at: "2026-10-25T00:00:00Z", end_at: "2026-10-24T12:00:00Z" }}
    />,
  );
  expect(screen.getByText("No results yet")).toBeVisible();
  expect(document.body).not.toHaveTextContent(/Results start|25 Oct 2026/);
  expect(document.body).not.toHaveTextContent("24 Oct 2026");
});
it.each(["2026-10-20T00:00:00Z", "2026-10-23T00:00:00Z"])(
  "keeps a valid reporting window ending %s",
  (end) => {
    render(
      <PerformanceCard {...data} period={{ start_at: "2026-10-20T00:00:00Z", end_at: end }} />,
    );
    expect(screen.queryByText(/Results start/)).toBeNull();
    expect(screen.getByText(/20 Oct 2026 →/)).toBeVisible();
  },
);
