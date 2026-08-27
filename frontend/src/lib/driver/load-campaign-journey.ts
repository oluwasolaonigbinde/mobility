import "server-only";

import type { components } from "@/lib/api/schema";
import { createApiClient, type ApiClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { getSessionToken } from "@/lib/auth/session";
import {
  projectDriverCampaignJourney,
  type DriverCampaignJourney,
  type DriverJourneyFacts,
  type DriverTrackerAssignment,
  type DriverTrackerTrip,
  type JourneyRead,
  type OfferAuthority,
  type VehicleAuthority,
} from "./campaign-journey";

type AssignmentStatus = components["schemas"]["CampaignAssignmentStatus"];
type AssignmentList = components["schemas"]["CampaignAssignmentListResponse"];

export interface LoadedDriverCampaignJourney {
  journey: DriverCampaignJourney;
  activationAssignment: DriverTrackerAssignment | null;
  currentTrip: DriverTrackerTrip | null;
  trackerAssignment: DriverTrackerAssignment | null;
}

async function read<T>(
  operation: Promise<{ data?: T }>,
  options: { notFoundIsAbsent?: boolean } = {},
): Promise<JourneyRead<T>> {
  try {
    const { data } = await operation;
    return data === undefined ? { state: "unavailable" } : { state: "available", value: data };
  } catch (error) {
    if (error instanceof ApiError && [401, 403].includes(error.status)) throw error;
    if (error instanceof ApiError && error.status === 404 && options.notFoundIsAbsent)
      return { state: "absent" };
    return { state: "unavailable" };
  }
}

function assignmentCount(source: JourneyRead<AssignmentList>): number | null {
  return source.state === "available" ? source.value.total : null;
}

function assignmentSummary(
  source: JourneyRead<components["schemas"]["ActiveCampaignAssignmentResponse"]>,
): JourneyRead<DriverTrackerAssignment | null> {
  if (source.state !== "available") return source;
  const assignment = source.value.assignment;
  if (!assignment) return { state: "available", value: null };
  return {
    state: "available",
    value: {
      id: assignment.id,
      campaignName: assignment.campaign?.name ?? "Campaign",
      plateNumber: assignment.vehicle?.plate_number ?? "Assigned vehicle",
      vehicleId: assignment.vehicle_id,
    },
  };
}

function tripSummary(
  source: JourneyRead<components["schemas"]["CurrentTripResponse"]>,
): JourneyRead<DriverTrackerTrip | null> {
  if (source.state === "unavailable") return source;
  if (source.state === "absent") return { state: "available", value: null };
  return {
    state: "available",
    value: source.value.trip ? { id: source.value.trip.id } : null,
  };
}

async function exactVehicleAuthority(
  api: ApiClient,
  vehicleId: string,
): Promise<JourneyRead<VehicleAuthority>> {
  const [vehicle, evidence] = await Promise.all([
    read(
      api.GET("/api/v1/driver/vehicles/{vehicle_id}", {
        params: { path: { vehicle_id: vehicleId } },
      }),
      { notFoundIsAbsent: true },
    ),
    read(
      api.GET("/api/v1/driver/vehicles/{vehicle_id}/evidence-current", {
        params: { path: { vehicle_id: vehicleId } },
      }),
      { notFoundIsAbsent: true },
    ),
  ]);
  if (vehicle.state === "unavailable" || evidence.state === "unavailable")
    return { state: "unavailable" };
  if (vehicle.state === "absent" || evidence.state === "absent") return { state: "absent" };
  return {
    state: "available",
    value: {
      approvedActiveCount:
        vehicle.value.status === "active" &&
        evidence.value.status === "approved" &&
        evidence.value.snapshot_trusted
          ? 1
          : 0,
      pendingCount: evidence.value.status === "pending_review" ? 1 : 0,
      rejectedCount: evidence.value.status === "rejected" ? 1 : 0,
      expiredCount: evidence.value.status === "expired" ? 1 : 0,
      inactiveCount: vehicle.value.status === "active" ? 0 : 1,
      assignmentVehicle: {
        plateNumber: vehicle.value.plate_number,
        vehicleStatus: vehicle.value.status,
        evidenceStatus: evidence.value.status,
        snapshotTrusted: evidence.value.snapshot_trusted,
      },
    },
  };
}

async function aggregateVehicleAuthority(
  api: ApiClient,
  vehicles: JourneyRead<components["schemas"]["VehicleListResponse"]>,
): Promise<JourneyRead<VehicleAuthority>> {
  if (vehicles.state !== "available") return vehicles;
  if (vehicles.value.total === 0) return { state: "absent" };
  if (vehicles.value.total !== vehicles.value.items.length) return { state: "unavailable" };

  const evidence = await Promise.all(
    vehicles.value.items.map((vehicle) =>
      read(
        api.GET("/api/v1/driver/vehicles/{vehicle_id}/evidence-current", {
          params: { path: { vehicle_id: vehicle.id } },
        }),
        { notFoundIsAbsent: true },
      ),
    ),
  );
  if (evidence.some((item) => item.state === "unavailable")) return { state: "unavailable" };

  return {
    state: "available",
    value: vehicles.value.items.reduce<VehicleAuthority>(
      (authority, vehicle, index) => {
        const current = evidence[index];
        if (current?.state === "available") {
          if (
            vehicle.status === "active" &&
            current.value.status === "approved" &&
            current.value.snapshot_trusted
          )
            authority.approvedActiveCount += 1;
          if (current.value.status === "pending_review") authority.pendingCount += 1;
          if (current.value.status === "rejected") authority.rejectedCount += 1;
          if (current.value.status === "expired") authority.expiredCount += 1;
        } else {
          authority.pendingCount += 1;
        }
        if (vehicle.status !== "active") authority.inactiveCount += 1;
        return authority;
      },
      {
        approvedActiveCount: 0,
        pendingCount: 0,
        rejectedCount: 0,
        expiredCount: 0,
        inactiveCount: 0,
      },
    ),
  };
}

export async function loadDriverCampaignJourney(): Promise<LoadedDriverCampaignJourney> {
  const api = createApiClient(await getSessionToken());
  const assignmentStatuses: AssignmentStatus[] = [
    "offered",
    "accepted",
    "active",
    "declined",
    "expired",
    "deactivated",
    "cancelled",
    "completed",
  ];
  const [profile, personPayee, vehicles, activeAssignment, currentTrip, ...assignmentReads] =
    await Promise.all([
      read(api.GET("/api/v1/driver/profile"), { notFoundIsAbsent: true }),
      read(api.GET("/api/v1/driver/kyc/current"), { notFoundIsAbsent: true }),
      read(api.GET("/api/v1/driver/vehicles", { params: { query: { limit: 100 } } })),
      read(api.GET("/api/v1/driver/campaign-assignments/active"), {
        notFoundIsAbsent: true,
      }),
      read(api.GET("/api/v1/driver/trips/current"), { notFoundIsAbsent: true }),
      ...assignmentStatuses.map((status) =>
        read(
          api.GET("/api/v1/driver/campaign-assignments", {
            params: { query: { limit: 1, status } },
          }),
        ),
      ),
    ] as const);

  const activation = assignmentSummary(activeAssignment);
  const trip = tripSummary(currentTrip);
  const counts = assignmentReads.map(assignmentCount);
  const offers: JourneyRead<OfferAuthority> = counts.some((count) => count === null)
    ? { state: "unavailable" }
    : {
        state: "available",
        value: Object.fromEntries(
          assignmentStatuses.map((status, index) => [status, counts[index] ?? 0]),
        ) as unknown as OfferAuthority,
      };
  const vehicle =
    activation.state === "available" && activation.value
      ? await exactVehicleAuthority(api, activation.value.vehicleId)
      : await aggregateVehicleAuthority(api, vehicles);

  const facts: DriverJourneyFacts = {
    profile:
      profile.state === "available"
        ? { state: "available", value: profile.value.onboarding_status }
        : profile,
    personPayee:
      personPayee.state === "available"
        ? { state: "available", value: personPayee.value.status }
        : personPayee,
    vehicle,
    offers,
    activation,
    trip,
  };
  const journey = projectDriverCampaignJourney(facts);
  const activationAssignment = activation.state === "available" ? activation.value : null;
  const currentTripSummary = trip.state === "available" ? trip.value : null;

  return {
    journey,
    activationAssignment,
    currentTrip: currentTripSummary,
    trackerAssignment: journey.canStart ? activationAssignment : null,
  };
}
