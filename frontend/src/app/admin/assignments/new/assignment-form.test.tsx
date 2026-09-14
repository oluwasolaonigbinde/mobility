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
        matching_version: "matching_v1",
        components: { driver_load: 0, vehicle_load: 0 },
      },
    ],
  });
  const { container } = render(<AssignmentForm />);
  await user.click(screen.getByRole("button", { name: "Find campaign" }));
  await user.click(await screen.findByRole("button", { name: /Pilot/ }));
  await user.type(screen.getByLabelText("Service city"), "Lagos");
  await user.click(screen.getByRole("button", { name: "Find candidates" }));
  expect(await screen.findByText("Ada Driver · ABC-123")).toBeInTheDocument();
  expect(container.querySelector('[name="recommendation_fingerprint"]')).toBeNull();
  await user.click(screen.getByRole("button", { name: "Choose candidate" }));
  expect(container.querySelector('[name="driver_profile_id"]')).toHaveValue("driver");
  expect(container.querySelector('[name="vehicle_id"]')).toHaveValue("vehicle");
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
