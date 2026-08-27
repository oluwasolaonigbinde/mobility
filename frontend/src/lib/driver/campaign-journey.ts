export type JourneyRead<T> =
  { state: "available"; value: T } | { state: "absent" } | { state: "unavailable" };

export interface DriverTrackerAssignment {
  id: string;
  campaignName: string;
  plateNumber: string;
  vehicleId: string;
}

export interface DriverTrackerTrip {
  id: string;
}

export interface VehicleAuthority {
  approvedActiveCount: number;
  pendingCount: number;
  rejectedCount: number;
  expiredCount: number;
  inactiveCount: number;
  assignmentVehicle?: {
    plateNumber: string;
    vehicleStatus: "pending" | "active" | "inactive" | "suspended";
    evidenceStatus: "pending_review" | "approved" | "rejected" | "expired";
    snapshotTrusted: boolean;
  };
}

export interface OfferAuthority {
  offered: number;
  accepted: number;
  active: number;
  declined: number;
  expired: number;
  deactivated: number;
  cancelled: number;
  completed: number;
}

export interface DriverJourneyFacts {
  profile: JourneyRead<"pending" | "active" | "suspended" | "rejected">;
  personPayee: JourneyRead<"pending_review" | "approved" | "rejected" | "expired">;
  vehicle: JourneyRead<VehicleAuthority>;
  offers: JourneyRead<OfferAuthority>;
  activation: JourneyRead<DriverTrackerAssignment | null>;
  trip: JourneyRead<DriverTrackerTrip | null>;
}

export type JourneyStepState = "complete" | "current" | "pending" | "blocked" | "degraded";

export interface DriverJourneyStep {
  id: "application" | "person_payee" | "vehicle" | "offer" | "activation" | "tracking";
  label: string;
  state: JourneyStepState;
  title: string;
  detail: string;
  href: string;
}

export interface DriverCampaignJourney {
  standing: "READY" | "TRACKING" | "PENDING" | "BLOCKED" | "DEGRADED";
  summary: string;
  canStart: boolean;
  hasCurrentTrip: boolean;
  steps: DriverJourneyStep[];
}

function profileStep(source: DriverJourneyFacts["profile"]): DriverJourneyStep {
  const base = {
    id: "application" as const,
    label: "Application & account",
    href: "/driver/profile",
  };
  if (source.state === "unavailable")
    return {
      ...base,
      state: "degraded",
      title: "Account status unavailable",
      detail: "Cardvert could not verify the current driver profile.",
    };
  if (source.state === "absent")
    return {
      ...base,
      state: "pending",
      title: "Invitation still pending",
      detail: "An application receipt is not approval or work access.",
    };
  if (source.value === "active")
    return {
      ...base,
      state: "complete",
      title: "Invited account active",
      detail: "Your authenticated driver profile is active.",
    };
  if (source.value === "pending")
    return {
      ...base,
      state: "current",
      title: "Application review pending",
      detail: "Operations has not activated this driver profile.",
    };
  return {
    ...base,
    state: "blocked",
    title: source.value === "rejected" ? "Application rejected" : "Account suspended",
    detail: "Campaign work and tracking remain unavailable.",
  };
}

function personPayeeStep(source: DriverJourneyFacts["personPayee"]): DriverJourneyStep {
  const base = { id: "person_payee" as const, label: "Person & payee", href: "/driver/profile" };
  if (source.state === "unavailable")
    return {
      ...base,
      state: "degraded",
      title: "Review status unavailable",
      detail: "Identity and payee approval could not be verified.",
    };
  if (source.state === "absent")
    return {
      ...base,
      state: "pending",
      title: "Evidence not submitted",
      detail: "Use the expiring onboarding code from the application email.",
    };
  if (source.value === "approved")
    return {
      ...base,
      state: "complete",
      title: "Person & payee approved",
      detail: "The current protected submission is approved.",
    };
  if (source.value === "pending_review")
    return {
      ...base,
      state: "current",
      title: "Person & payee under review",
      detail: "Approval is pending; this does not grant work eligibility.",
    };
  return {
    ...base,
    state: "blocked",
    title:
      source.value === "expired" ? "Person & payee approval expired" : "Person & payee rejected",
    detail: "Submit a new governed revision before campaign work.",
  };
}

function vehicleStep(source: DriverJourneyFacts["vehicle"]): DriverJourneyStep {
  const base = { id: "vehicle" as const, label: "Vehicle review", href: "/driver/profile" };
  if (source.state === "unavailable")
    return {
      ...base,
      state: "degraded",
      title: "Vehicle status unavailable",
      detail: "Cardvert cannot verify current vehicle evidence.",
    };
  if (source.state === "absent")
    return {
      ...base,
      state: "pending",
      title: "Vehicle evidence not approved",
      detail: "A current approved car and evidence revision are required.",
    };

  const exact = source.value.assignmentVehicle;
  if (exact) {
    if (
      exact.vehicleStatus === "active" &&
      exact.evidenceStatus === "approved" &&
      exact.snapshotTrusted
    ) {
      return {
        ...base,
        state: "complete",
        title: `${exact.plateNumber} approved`,
        detail: "The exact campaign vehicle has current approved evidence.",
      };
    }
    if (
      ["rejected", "expired"].includes(exact.evidenceStatus) ||
      exact.vehicleStatus === "suspended"
    ) {
      return {
        ...base,
        state: "blocked",
        title:
          exact.evidenceStatus === "expired"
            ? `${exact.plateNumber} evidence expired`
            : `${exact.plateNumber} is not approved`,
        detail: "The assignment vehicle cannot be treated as work-ready.",
      };
    }
    return {
      ...base,
      state: exact.evidenceStatus === "approved" ? "degraded" : "current",
      title: `${exact.plateNumber} review incomplete`,
      detail: "Current vehicle and evidence authority must both pass.",
    };
  }

  if (source.value.approvedActiveCount > 0)
    return {
      ...base,
      state: "complete",
      title: `${source.value.approvedActiveCount} approved vehicle${source.value.approvedActiveCount === 1 ? "" : "s"}`,
      detail: "A current active car has approved evidence.",
    };
  if (source.value.rejectedCount > 0 || source.value.expiredCount > 0)
    return {
      ...base,
      state: "blocked",
      title:
        source.value.expiredCount > 0 ? "Vehicle evidence expired" : "Vehicle evidence rejected",
      detail: "A new governed evidence revision is required.",
    };
  return {
    ...base,
    state: "current",
    title: "Vehicle review pending",
    detail: "Operations has not approved a current active vehicle.",
  };
}

function offerDetail(offers: OfferAuthority): string {
  const parts = [
    offers.offered ? `${offers.offered} awaiting your decision` : "",
    offers.accepted ? `${offers.accepted} accepted and awaiting activation` : "",
    offers.expired ? `${offers.expired} expired` : "",
    offers.declined ? `${offers.declined} declined` : "",
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "No current offer is available.";
}

function offerStep(source: DriverJourneyFacts["offers"]): DriverJourneyStep {
  const base = { id: "offer" as const, label: "Campaign offer", href: "/driver/assignments" };
  if (source.state === "unavailable")
    return {
      ...base,
      state: "degraded",
      title: "Offer status unavailable",
      detail: "Cardvert could not verify current offer decisions.",
    };
  if (source.state === "absent")
    return {
      ...base,
      state: "pending",
      title: "No campaign offers",
      detail: "No driver profile offers are available.",
    };
  if (source.value.active > 1)
    return {
      ...base,
      state: "degraded",
      title: "Offer authority conflict",
      detail: "More than one active assignment was reported.",
    };
  if (source.value.active === 1)
    return {
      ...base,
      state: "complete",
      title: "Offer accepted",
      detail: offerDetail(source.value),
    };
  if (source.value.accepted > 0)
    return {
      ...base,
      state: "complete",
      title: "Offer accepted",
      detail: offerDetail(source.value),
    };
  if (source.value.offered > 0)
    return {
      ...base,
      state: "current",
      title: "Offer decision needed",
      detail: offerDetail(source.value),
    };
  return {
    ...base,
    state: "pending",
    title:
      source.value.expired > 0 ? "No current offer — previous offer expired" : "No current offer",
    detail: offerDetail(source.value),
  };
}

function activationStep(
  activation: DriverJourneyFacts["activation"],
  offers: DriverJourneyFacts["offers"],
): DriverJourneyStep {
  const base = {
    id: "activation" as const,
    label: "Admin activation",
    href: "/driver/assignments",
  };
  if (activation.state === "unavailable")
    return {
      ...base,
      state: "degraded",
      title: "Activation status unavailable",
      detail: "A new trip cannot start until activation authority is verified.",
    };
  if (activation.state === "absent" || activation.value === null) {
    const accepted = offers.state === "available" ? offers.value.accepted : 0;
    if (offers.state === "available" && offers.value.active > 0)
      return {
        ...base,
        state: "degraded",
        title: "Activation authority conflict",
        detail: "Assignment history looks active but canonical activation is absent.",
      };
    return {
      ...base,
      state: accepted > 0 ? "current" : "pending",
      title: accepted > 0 ? "Waiting for admin activation" : "Not activated",
      detail: "Offer acceptance alone does not grant campaign work.",
    };
  }
  if (offers.state !== "available" || offers.value.active !== 1)
    return {
      ...base,
      state: "degraded",
      title: "Activation authority conflict",
      detail: "Assignment sources disagree; a new trip is withheld.",
    };
  return {
    ...base,
    state: "complete",
    title: "Campaign activated",
    detail: `${activation.value.campaignName} is active for ${activation.value.plateNumber}.`,
  };
}

export function projectDriverCampaignJourney(facts: DriverJourneyFacts): DriverCampaignJourney {
  const steps = [
    profileStep(facts.profile),
    personPayeeStep(facts.personPayee),
    vehicleStep(facts.vehicle),
    offerStep(facts.offers),
    activationStep(facts.activation, facts.offers),
  ];
  const hasCurrentTrip = facts.trip.state === "available" && facts.trip.value !== null;
  const prerequisitesComplete = steps.every((step) => step.state === "complete");
  const canStart =
    facts.trip.state === "available" && facts.trip.value === null && prerequisitesComplete;
  const tracking: DriverJourneyStep =
    facts.trip.state === "unavailable"
      ? {
          id: "tracking",
          label: "Screen-on tracking",
          state: "degraded",
          title: "Trip authority unavailable",
          detail: "Cardvert cannot prove whether a trip is already active, so Start is withheld.",
          href: "/driver/track",
        }
      : hasCurrentTrip
        ? {
            id: "tracking",
            label: "Screen-on tracking",
            state: "current",
            title: "Trip in progress",
            detail: "Open tracking to manage safe capture, reconciliation or End.",
            href: "/driver/track",
          }
        : canStart
          ? {
              id: "tracking",
              label: "Screen-on tracking",
              state: "current",
              title: "Ready for explicit Start",
              detail: "Start remains subject to the live PWA capability and server checks.",
              href: "/driver/track",
            }
          : {
              id: "tracking",
              label: "Screen-on tracking",
              state: "pending",
              title: "Tracking locked",
              detail: "Complete the governed stages above before a new trip can start.",
              href: "/driver/track",
            };
  const allSteps = [...steps, tracking];

  if (hasCurrentTrip)
    return {
      standing: "TRACKING",
      summary: "A server-confirmed trip is in progress. Keep Cardvert visible on screen.",
      canStart: false,
      hasCurrentTrip: true,
      steps: allSteps,
    };
  if (allSteps.some((step) => step.state === "degraded"))
    return {
      standing: "DEGRADED",
      summary: "Some authority could not be verified. Cardvert will not claim readiness.",
      canStart: false,
      hasCurrentTrip: false,
      steps: allSteps,
    };
  if (allSteps.some((step) => step.state === "blocked"))
    return {
      standing: "BLOCKED",
      summary: "A rejected, expired or suspended stage blocks campaign work.",
      canStart: false,
      hasCurrentTrip: false,
      steps: allSteps,
    };
  if (canStart)
    return {
      standing: "READY",
      summary: "Backend onboarding, vehicle, offer and activation authority are current.",
      canStart: true,
      hasCurrentTrip: false,
      steps: allSteps,
    };
  return {
    standing: "PENDING",
    summary: "Campaign work remains unavailable until every server-governed stage completes.",
    canStart: false,
    hasCurrentTrip: false,
    steps: allSteps,
  };
}
