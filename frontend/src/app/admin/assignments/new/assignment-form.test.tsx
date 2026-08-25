import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AssignmentForm } from "./assignment-form";

const mocks = vi.hoisted(() => ({
  create: vi.fn(),
  recommendations: vi.fn(),
}));

vi.mock("../actions", () => ({
  createAssignmentAction: mocks.create,
  listAssignmentRecommendationsAction: mocks.recommendations,
}));

const CAMPAIGN_ID = "00000000-0000-4000-8000-000000000001";
const DRIVER_ID = "00000000-0000-4000-8000-000000000002";
const OTHER_DRIVER_ID = "00000000-0000-4000-8000-000000000003";
const VEHICLE_ID = "00000000-0000-4000-8000-000000000004";

describe("AssignmentForm recommendations", () => {
  beforeEach(() => {
    mocks.create.mockReset();
    mocks.create.mockResolvedValue({});
    mocks.recommendations.mockReset();
    mocks.recommendations.mockResolvedValue({
      candidates: [
        {
          rank: 1,
          driver_profile_id: DRIVER_ID,
          driver_name: "Ada Driver",
          vehicle_id: VEHICLE_ID,
          vehicle_plate_number: "ABC-123",
          vehicle_make: "Toyota",
          vehicle_model: "Corolla",
          service_city: "Lagos",
          vehicle_type: "car",
          matching_version: "matching_v1",
          fingerprint: "a".repeat(64),
          components: {
            vehicle_load: 0,
            driver_load: 1,
            active_tracking_seconds: 3600,
            latest_computed_at: "2026-08-25T10:00:00Z",
          },
        },
      ],
    });
  });

  it("loads ranked cars but waits for an explicit admin choice", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <AssignmentForm
        campaigns={[{ id: CAMPAIGN_ID, label: "Pilot (scheduled)" }]}
        drivers={[
          { id: DRIVER_ID, label: "Ada Driver — Lagos", driverProfileId: DRIVER_ID },
          {
            id: OTHER_DRIVER_ID,
            label: "Other Driver — Lagos",
            driverProfileId: OTHER_DRIVER_ID,
          },
        ]}
        vehicles={[
          {
            id: VEHICLE_ID,
            label: "ABC-123 — Toyota Corolla",
            driverProfileId: DRIVER_ID,
          },
        ]}
      />,
    );

    await user.selectOptions(screen.getByLabelText("Campaign"), CAMPAIGN_ID);
    await user.type(screen.getByLabelText("Service city"), " Lagos ");
    await user.click(screen.getByRole("button", { name: "Find candidates" }));

    expect(await screen.findByText(/#1 · Ada Driver · ABC-123/)).toBeInTheDocument();
    expect(mocks.recommendations).toHaveBeenCalledWith({
      campaign_id: CAMPAIGN_ID,
      service_city: " Lagos ",
    });
    expect(container.querySelector('[name="recommendation_fingerprint"]')).toBeNull();
    expect(screen.getByLabelText("Driver")).toHaveValue("");

    await user.click(screen.getByRole("button", { name: "Choose candidate" }));

    expect(screen.getByLabelText("Driver")).toHaveValue(DRIVER_ID);
    expect(screen.getByLabelText(/Vehicle/)).toHaveValue(VEHICLE_ID);
    expect(container.querySelector('[name="recommendation_fingerprint"]')).toHaveValue(
      "a".repeat(64),
    );
    expect(screen.getByRole("button", { name: "Candidate selected" })).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Driver"), OTHER_DRIVER_ID);
    await waitFor(() =>
      expect(container.querySelector('[name="recommendation_fingerprint"]')).toBeNull(),
    );
  });
});
