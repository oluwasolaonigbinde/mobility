import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { JobVisual } from "./job-visual";
import { frozenJob } from "@/lib/driver/frozen-job";
vi.mock("@/components/campaigns/campaign-map", () => ({
  CampaignMap: ({ areas }: { areas: { name: string }[] }) => (
    <div aria-label="Real job boundaries">{areas.map((area) => area.name).join(", ")}</div>
  ),
}));

it("shows paying areas and explicitly named exclusions", () => {
  render(
    <JobVisual
      job={frozenJob({
        zones: { target: [{ name: "Wuse II" }], exclusion: [{ name: "Airport restricted area" }] },
      })}
    />,
  );
  expect(screen.getByText("Wuse II")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Avoid" })).toBeInTheDocument();
  expect(screen.getByText("Airport restricted area")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "The advert on your car" })).toBeInTheDocument();
  expect(screen.getByRole("img", { name: /Illustration/ })).toBeInTheDocument();
});

it("warns when exclusions are unreadable even if paying areas are available", () => {
  render(
    <JobVisual job={frozenJob({ zones: { target: [{ name: "Wuse II" }], exclusion: [{}] } })} />,
  );
  expect(screen.getByText("Wuse II")).toBeInTheDocument();
  expect(screen.getByText(/Areas to avoid couldn't be loaded/)).toBeInTheDocument();
});

it("does not imply restrictions are unavailable when the frozen list is explicitly empty", () => {
  render(
    <JobVisual job={frozenJob({ zones: { target: [{ name: "Wuse II" }], exclusion: [] } })} />,
  );
  expect(screen.queryByText(/Areas to avoid|Avoid:/)).not.toBeInTheDocument();
});
it("shows only the existing frozen target and Avoid shapes above the area chips", () => {
  render(
    <JobVisual
      job={frozenJob({
        zones: {
          target: [{ name: "Wuse", wkt: "POLYGON((7 9,7.5 9,7.5 9.5,7 9))" }],
          exclusion: [{ name: "Restricted", wkt: "POLYGON((7.1 9.1,7.2 9.1,7.2 9.2,7.1 9.1))" }],
        },
      })}
    />,
  );
  expect(screen.getByLabelText("Real job boundaries")).toHaveTextContent("Wuse, Restricted");
});
