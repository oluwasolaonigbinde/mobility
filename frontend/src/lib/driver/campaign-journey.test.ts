import { describe, expect, it } from "vitest";
import {
  projectDriverCampaignJourney,
  type DriverJourneyFacts,
  type OfferAuthority,
} from "./campaign-journey";

const assignment = {
  id: "22222222-2222-4222-8222-222222222222",
  campaignName: "Abuja Pilot",
  plateNumber: "ABC-123",
  vehicleId: "33333333-3333-4333-8333-333333333333",
};

const emptyOffers: OfferAuthority = {
  offered: 0,
  accepted: 0,
  active: 0,
  declined: 0,
  expired: 0,
  deactivated: 0,
  cancelled: 0,
  completed: 0,
};

function readyFacts(): DriverJourneyFacts {
  return {
    profile: { state: "available", value: "active" },
    personPayee: { state: "available", value: "approved" },
    vehicle: {
      state: "available",
      value: {
        approvedActiveCount: 1,
        pendingCount: 0,
        rejectedCount: 0,
        expiredCount: 0,
        inactiveCount: 0,
        assignmentVehicle: {
          plateNumber: "ABC-123",
          vehicleStatus: "active",
          evidenceStatus: "approved",
          snapshotTrusted: true,
        },
      },
    },
    offers: { state: "available", value: { ...emptyOffers, active: 1 } },
    activation: { state: "available", value: assignment },
    trip: { state: "available", value: null },
  };
}

describe("driver campaign journey authority projection", () => {
  it("claims readiness only when every current authority agrees", () => {
    const journey = projectDriverCampaignJourney(readyFacts());

    expect(journey.standing).toBe("READY");
    expect(journey.canStart).toBe(true);
    expect(journey.steps.map((step) => step.state)).toEqual([
      "complete",
      "complete",
      "complete",
      "complete",
      "complete",
      "current",
    ]);
  });

  it.each(["rejected", "expired"] as const)(
    "blocks readiness when current person/payee authority is %s",
    (status) => {
      const facts = readyFacts();
      facts.personPayee = { state: "available", value: status };

      const journey = projectDriverCampaignJourney(facts);

      expect(journey.standing).toBe("BLOCKED");
      expect(journey.canStart).toBe(false);
      expect(journey.steps.find((step) => step.id === "person_payee")?.state).toBe("blocked");
    },
  );

  it("does not trust an active vehicle whose current evidence expired", () => {
    const facts = readyFacts();
    facts.vehicle = {
      state: "available",
      value: {
        approvedActiveCount: 0,
        pendingCount: 0,
        rejectedCount: 0,
        expiredCount: 1,
        inactiveCount: 0,
        assignmentVehicle: {
          plateNumber: "ABC-123",
          vehicleStatus: "active",
          evidenceStatus: "expired",
          snapshotTrusted: true,
        },
      },
    };

    const journey = projectDriverCampaignJourney(facts);

    expect(journey.standing).toBe("BLOCKED");
    expect(journey.canStart).toBe(false);
    expect(journey.steps.find((step) => step.id === "vehicle")?.title).toMatch(/expired/i);
  });

  it("degrades when current evidence cannot be read, even if other rows look active", () => {
    const facts = readyFacts();
    facts.vehicle = { state: "unavailable" };

    const journey = projectDriverCampaignJourney(facts);

    expect(journey.standing).toBe("DEGRADED");
    expect(journey.canStart).toBe(false);
    expect(journey.summary).not.toMatch(/ready/i);
  });

  it("degrades when assignment history looks active but canonical activation is absent", () => {
    const facts = readyFacts();
    facts.activation = { state: "available", value: null };

    const journey = projectDriverCampaignJourney(facts);

    expect(journey.standing).toBe("DEGRADED");
    expect(journey.canStart).toBe(false);
    expect(journey.steps.find((step) => step.id === "activation")?.title).toMatch(/conflict/i);
  });

  it("keeps a current trip manageable through degraded activation reads", () => {
    const facts = readyFacts();
    facts.activation = { state: "unavailable" };
    facts.trip = { state: "available", value: { id: "11111111-1111-4111-8111-111111111111" } };

    const journey = projectDriverCampaignJourney(facts);

    expect(journey.standing).toBe("TRACKING");
    expect(journey.hasCurrentTrip).toBe(true);
    expect(journey.canStart).toBe(false);
    expect(journey.steps.find((step) => step.id === "tracking")?.title).toBe("Trip in progress");
  });

  it("shows aggregate offer decisions without inventing a current item", () => {
    const facts = readyFacts();
    facts.offers = {
      state: "available",
      value: { ...emptyOffers, offered: 2, accepted: 1 },
    };
    facts.activation = { state: "available", value: null };

    const journey = projectDriverCampaignJourney(facts);
    const offer = journey.steps.find((step) => step.id === "offer");

    expect(journey.standing).toBe("PENDING");
    expect(offer?.detail).toContain("2 awaiting your decision");
    expect(offer?.detail).toContain("1 accepted and awaiting activation");
  });

  it("withholds Start when current-trip authority is unavailable", () => {
    const facts = readyFacts();
    facts.trip = { state: "unavailable" };

    const journey = projectDriverCampaignJourney(facts);

    expect(journey.standing).toBe("DEGRADED");
    expect(journey.canStart).toBe(false);
    expect(journey.steps.find((step) => step.id === "tracking")?.title).toMatch(/unavailable/i);
  });
});
