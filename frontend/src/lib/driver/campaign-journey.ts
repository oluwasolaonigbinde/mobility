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
      detail: "Cardvert couldn't check your driver account right now.",
    };
  if (source.state === "absent")
    return {
      ...base,
      state: "pending",
      title: "Invitation still pending",
      detail: "Your application was received. That isn't an approval yet.",
    };
  if (source.value === "active")
    return {
      ...base,
      state: "complete",
      title: "Account active",
      detail: "Your driver account is set up.",
    };
  if (source.value === "pending")
    return {
      ...base,
      state: "current",
      title: "Application under review",
      detail: "Cardvert hasn't approved your driver profile yet.",
    };
  return {
    ...base,
    state: "blocked",
    title: source.value === "rejected" ? "Application rejected" : "Account suspended",
    detail: "You can't take campaign work or record trips right now.",
  };
}

function personPayeeStep(source: DriverJourneyFacts["personPayee"]): DriverJourneyStep {
  const base = {
    id: "person_payee" as const,
    label: "Identity & bank details",
    href: "/driver/profile",
  };
  if (source.state === "unavailable")
    return {
      ...base,
      state: "degraded",
      title: "Review status unavailable",
      detail: "Cardvert couldn't check your identity and bank details right now.",
    };
  if (source.state === "absent")
    return {
      ...base,
      state: "pending",
      title: "Details not sent yet",
      detail: "Use the access code in your application email to send them.",
    };
  if (source.value === "approved")
    return {
      ...base,
      state: "complete",
      title: "Identity and bank details approved",
      detail: "Nothing more to do here.",
    };
  if (source.value === "pending_review")
    return {
      ...base,
      state: "current",
      title: "Identity and bank details in review",
      detail: "You can't take campaign work until they're approved.",
    };
  return {
    ...base,
    state: "blocked",
    title:
      source.value === "expired"
        ? "Identity and bank approval expired"
        : "Identity and bank details rejected",
    detail: "Updated details must be sent and approved before campaign work.",
  };
}

function vehicleStep(source: DriverJourneyFacts["vehicle"]): DriverJourneyStep {
  const base = { id: "vehicle" as const, label: "Car approval", href: "/driver/profile" };
  if (source.state === "unavailable")
    return {
      ...base,
      state: "degraded",
      title: "Vehicle status unavailable",
      detail: "Cardvert couldn't check your car's approval right now.",
    };
  if (source.state === "absent")
    return {
      ...base,
      state: "pending",
      title: "Car not approved yet",
      detail: "You need an approved car with current documents.",
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
        detail: "The car for this campaign is approved.",
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
            ? `${exact.plateNumber} documents expired`
            : `${exact.plateNumber} is not approved`,
        detail: "This car can't be used for campaign work until it's approved again.",
      };
    }
    return {
      ...base,
      state: exact.evidenceStatus === "approved" ? "degraded" : "current",
      title: `${exact.plateNumber} review not finished`,
      detail: "The car and its documents both need to be approved.",
    };
  }

  if (source.value.approvedActiveCount > 0)
    return {
      ...base,
      state: "complete",
      title: `${source.value.approvedActiveCount} approved vehicle${source.value.approvedActiveCount === 1 ? "" : "s"}`,
      detail: "You have a car ready for campaign work.",
    };
  if (source.value.rejectedCount > 0 || source.value.expiredCount > 0)
    return {
      ...base,
      state: "blocked",
      title: source.value.expiredCount > 0 ? "Car documents expired" : "Car documents rejected",
      detail: "Updated car documents must be sent and approved.",
    };
  return {
    ...base,
    state: "current",
    title: "Car review in progress",
    detail: "Cardvert hasn't approved a car yet.",
  };
}

function offerDetail(offers: OfferAuthority): string {
  const parts = [
    offers.offered ? `${offers.offered} new offer${offers.offered === 1 ? "" : "s"} to review` : "",
    offers.accepted ? `${offers.accepted} accepted, waiting to start` : "",
    offers.expired ? `${offers.expired} expired` : "",
    offers.declined ? `${offers.declined} declined` : "",
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "No offers right now.";
}

function offerStep(source: DriverJourneyFacts["offers"]): DriverJourneyStep {
  const base = { id: "offer" as const, label: "Campaign offer", href: "/driver/assignments" };
  if (source.state === "unavailable")
    return {
      ...base,
      state: "degraded",
      title: "Offer status unavailable",
      detail: "Cardvert couldn't check your offers right now.",
    };
  if (source.state === "absent")
    return {
      ...base,
      state: "pending",
      title: "No campaign offers",
      detail: "You don't have any offers yet.",
    };
  if (source.value.active > 1)
    return {
      ...base,
      state: "degraded",
      title: "Job details conflict",
      detail: "More than one campaign shows as running, so starting a trip is paused.",
    };
  if (source.value.active === 1)
    return {
      ...base,
      state: "complete",
      title: "Offer accepted",
      detail: source.value.offered
        ? `Your accepted job is running · ${offerDetail(source.value)}`
        : "Your accepted job is running.",
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
      title: "Offer waiting for your decision",
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
    label: "Campaign start",
    href: "/driver/assignments",
  };
  if (activation.state === "unavailable")
    return {
      ...base,
      state: "degraded",
      title: "Campaign start status unavailable",
      detail: "A new trip can't start until this is checked.",
    };
  if (activation.state === "absent" || activation.value === null) {
    const accepted = offers.state === "available" ? offers.value.accepted : 0;
    if (offers.state === "available" && offers.value.active > 0)
      return {
        ...base,
        state: "degraded",
        title: "Job details conflict",
        detail:
          "Your job shows as running but its campaign start is missing, so starting a trip is paused.",
      };
    return {
      ...base,
      state: accepted > 0 ? "current" : "pending",
      title: accepted > 0 ? "Waiting for Cardvert to start the campaign" : "Not started",
      detail:
        "Accepting an offer doesn't start campaign work. Cardvert starts it once installation is checked.",
    };
  }
  if (offers.state !== "available" || offers.value.active !== 1)
    return {
      ...base,
      state: "degraded",
      title: "Job details conflict",
      detail: "Your job details don't match, so starting a trip is paused.",
    };
  return {
    ...base,
    state: "complete",
    title: "Campaign activated",
    detail: `${activation.value.campaignName} is running on ${activation.value.plateNumber}.`,
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
          label: "Ready to drive",
          state: "degraded",
          title: "Trip status unavailable",
          detail: "Cardvert can't tell whether a trip is already running, so Start is paused.",
          href: "/driver/track",
        }
      : hasCurrentTrip
        ? {
            id: "tracking",
            label: "Ready to drive",
            state: "current",
            title: "Trip in progress",
            detail: "Open Track to keep recording or to end the trip.",
            href: "/driver/track",
          }
        : canStart
          ? {
              id: "tracking",
              label: "Ready to drive",
              state: "current",
              title: "Ready to start",
              detail: "Press Start on the Track page when you begin driving.",
              href: "/driver/track",
            }
          : {
              id: "tracking",
              label: "Ready to drive",
              state: "pending",
              title: "Not ready yet",
              detail: "Finish the steps above before you can start a trip.",
              href: "/driver/track",
            };
  const allSteps = [...steps, tracking];

  if (hasCurrentTrip)
    return {
      standing: "TRACKING",
      summary: "A trip is in progress. Keep Cardvert open on screen while you drive.",
      canStart: false,
      hasCurrentTrip: true,
      steps: allSteps,
    };
  if (allSteps.some((step) => step.state === "degraded"))
    return {
      standing: "DEGRADED",
      summary:
        "Some details could not be verified, so starting a trip is paused. Refresh to try again.",
      canStart: false,
      hasCurrentTrip: false,
      steps: allSteps,
    };
  if (allSteps.some((step) => step.state === "blocked"))
    return {
      standing: "BLOCKED",
      summary: "Something below needs attention before you can take campaign work.",
      canStart: false,
      hasCurrentTrip: false,
      steps: allSteps,
    };
  if (canStart)
    return {
      standing: "READY",
      summary: "You're ready to drive.",
      canStart: true,
      hasCurrentTrip: false,
      steps: allSteps,
    };
  return {
    standing: "PENDING",
    summary: "A few steps are still in progress before you can start trips.",
    canStart: false,
    hasCurrentTrip: false,
    steps: allSteps,
  };
}
