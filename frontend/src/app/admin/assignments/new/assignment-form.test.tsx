import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { AssignmentForm } from "./assignment-form";
const mocks = vi.hoisted(() => ({
  create: vi.fn(async () => ({})),
  recommendations: vi.fn(),
  search: vi.fn(),
}));
vi.mock("../actions", () => ({
  createAssignmentAction: mocks.create,
  listAssignmentRecommendationsAction: mocks.recommendations,
}));
vi.mock("../../queue-options", () => ({ searchOperatorOptions: mocks.search }));
it("requires an explicit recommended candidate and clears its evidence after a manual driver choice", async () => {
  const user = userEvent.setup();
  mocks.search.mockImplementation(async ({ kind }) => ({
    total: 1,
    items: [
      {
        id: kind === "campaign" ? "campaign" : "other",
        label: kind === "campaign" ? "Pilot" : "Other driver",
        detail: "Named context",
      },
    ],
  }));
  mocks.recommendations.mockResolvedValue({
    candidates: [
      {
        driver_profile_id: "driver",
        vehicle_id: "vehicle",
        driver_name: "Ada Driver",
        vehicle_plate_number: "ABC-123",
        service_city: "Lagos",
        fingerprint: "a".repeat(64),
        vehicle_type: "car",
        matching_version: "matching_v1",
        components: { driver_load: 0, vehicle_load: 0 },
      },
    ],
  });
  const { container } = render(<AssignmentForm />);
  await user.click(screen.getByRole("button", { name: "Find campaign" }));
  await user.click(await screen.findByRole("button", { name: /Pilot/ }));
  await user.type(screen.getByLabelText("City"), "Lagos");
  await user.click(screen.getByRole("button", { name: "Find drivers" }));
  expect(await screen.findByText("Ada Driver · ABC-123")).toBeInTheDocument();
  expect(container.querySelector('[name="recommendation_fingerprint"]')).toBeNull();
  await user.click(screen.getByRole("button", { name: "Choose" }));
  expect(container.querySelector('[name="driver_profile_id"]')).toHaveValue("driver");
  expect(container.querySelector('[name="vehicle_id"]')).toHaveValue("vehicle");
  expect(container.querySelector('[name="recommendation_vehicle_type"]')).toHaveValue("car");
  expect(container.querySelector('[name="recommendation_fingerprint"]')).toHaveValue(
    "a".repeat(64),
  );
  await user.click(screen.getByRole("button", { name: "Find driver" }));
  await user.click(await screen.findByRole("button", { name: /Other driver/ }));
  await waitFor(() =>
    expect(container.querySelector('[name="recommendation_fingerprint"]')).toBeNull(),
  );
  expect(container.querySelector('[name="vehicle_id"]')).toHaveValue("");
});

const CAMPAIGN = "00000000-0000-4000-8000-0000000000c1";

async function findIn(city: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("City"), city);
  await user.click(screen.getByRole("button", { name: "Find drivers" }));
  return user;
}

it("shows no result message before any search", () => {
  render(<AssignmentForm campaignId={CAMPAIGN} />);
  expect(screen.queryByText(/No drivers found/)).toBeNull();
});

it("says when a search finds no drivers, and hides it once the city changes", async () => {
  mocks.recommendations.mockResolvedValue({ candidates: [] });
  render(<AssignmentForm campaignId={CAMPAIGN} />);
  const user = await findIn("Lagos");
  expect(
    await screen.findByText("No drivers found for this campaign in Lagos."),
  ).toBeInTheDocument();
  await user.type(screen.getByLabelText("City"), "x");
  expect(screen.queryByText(/No drivers found/)).toBeNull();
});

it("names the chosen driver when they have no match", async () => {
  mocks.recommendations.mockResolvedValue({ candidates: [] });
  render(<AssignmentForm campaignId={CAMPAIGN} driverId="driver" />);
  await findIn("Abuja");
  expect(
    await screen.findByText("This driver has no match for this campaign in Abuja."),
  ).toBeInTheDocument();
});

it("shows no empty message while searching or after an error", async () => {
  let finish: (value: unknown) => void = () => {};
  mocks.recommendations.mockReturnValueOnce(new Promise((resolve) => (finish = resolve)));
  render(<AssignmentForm campaignId={CAMPAIGN} />);
  await findIn("Lagos");
  expect(await screen.findByRole("button", { name: "Finding…" })).toBeDisabled();
  expect(screen.queryByText(/No drivers found/)).toBeNull();
  finish({ error: "That didn't work. Try again." });
  expect(await screen.findByRole("alert")).toHaveTextContent("That didn't work. Try again.");
  expect(screen.queryByText(/No drivers found/)).toBeNull();
});

it("drops a late reply from a search for an earlier campaign", async () => {
  mocks.search.mockResolvedValue({
    total: 2,
    items: [
      { id: "first", label: "First campaign", detail: "One" },
      { id: "second", label: "Second campaign", detail: "Two" },
    ],
  });
  let finish: (value: unknown) => void = () => {};
  mocks.recommendations.mockReturnValueOnce(new Promise((resolve) => (finish = resolve)));
  const user = userEvent.setup();
  render(<AssignmentForm />);
  await user.click(screen.getByRole("button", { name: "Find campaign" }));
  await user.click(await screen.findByRole("button", { name: /First campaign/ }));
  await user.type(screen.getByLabelText("City"), "Lagos");
  await user.click(screen.getByRole("button", { name: "Find drivers" }));
  await user.click(screen.getByRole("button", { name: /Second campaign/ }));
  finish({
    candidates: [
      {
        driver_profile_id: "driver",
        vehicle_id: "vehicle",
        driver_name: "Late Driver",
        vehicle_plate_number: "OLD-1",
        service_city: "Lagos",
        fingerprint: "b".repeat(64),
        vehicle_type: "car",
        matching_version: "matching_v1",
        components: { driver_load: 0, vehicle_load: 0 },
      },
    ],
  });
  await waitFor(() => expect(screen.getByRole("button", { name: "Find drivers" })).toBeEnabled());
  expect(screen.queryByText(/Late Driver/)).toBeNull();
});

const LATE = {
  driver_profile_id: "driver",
  vehicle_id: "vehicle",
  driver_name: "Late Driver",
  vehicle_plate_number: "OLD-1",
  service_city: "Lagos",
  fingerprint: "c".repeat(64),
  vehicle_type: "car",
  matching_version: "matching_v1",
  components: { driver_load: 0, vehicle_load: 0 },
};

it.each([
  ["a non-empty reply", { candidates: [LATE] }],
  ["a failed reply", { error: "That didn't work. Try again." }],
])("hides %s that arrives after the city was edited", async (_name, reply) => {
  let finish: (value: unknown) => void = () => {};
  mocks.recommendations.mockReturnValueOnce(new Promise((resolve) => (finish = resolve)));
  render(<AssignmentForm campaignId={CAMPAIGN} />);
  const user = await findIn("Lagos");
  await user.type(screen.getByLabelText("City"), "x");
  finish(reply);
  await waitFor(() => expect(screen.getByRole("button", { name: "Find drivers" })).toBeEnabled());
  expect(screen.queryByText(/Late Driver/)).toBeNull();
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.queryByText(/No drivers found/)).toBeNull();
});

it("drops results and the chosen recommendation when the driver scope changes", async () => {
  mocks.recommendations.mockResolvedValue({ candidates: [LATE] });
  const { container, rerender } = render(
    <AssignmentForm campaignId={CAMPAIGN} driverId="driver" />,
  );
  const user = await findIn("Lagos");
  await user.click(await screen.findByRole("button", { name: "Choose" }));
  expect(container.querySelector('[name="recommendation_fingerprint"]')).toHaveValue(
    "c".repeat(64),
  );
  rerender(<AssignmentForm campaignId={CAMPAIGN} driverId="other-driver" />);
  expect(screen.queryByText(/Late Driver · OLD-1/)).toBeNull();
  expect(container.querySelector('[name="recommendation_fingerprint"]')).toBeNull();
});

it("clears the chosen recommendation when the city is edited", async () => {
  mocks.recommendations.mockResolvedValue({ candidates: [LATE] });
  const { container } = render(<AssignmentForm campaignId={CAMPAIGN} />);
  const user = await findIn("Lagos");
  await user.click(await screen.findByRole("button", { name: "Choose" }));
  expect(container.querySelector('[name="recommendation_fingerprint"]')).not.toBeNull();
  await user.type(screen.getByLabelText("City"), "x");
  expect(container.querySelector('[name="recommendation_fingerprint"]')).toBeNull();
});
