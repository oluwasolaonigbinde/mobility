import { readDriver } from "../../entity-reads";
import DriverHub, { type DriverHubQuery } from "../driver-hub";
export default async function DriverPage({
  params,
  searchParams,
}: {
  params: Promise<{ driverId: string }>;
  searchParams: Promise<DriverHubQuery>;
}) {
  return <DriverHub driverId={(await params).driverId} query={await searchParams} />;
}

export async function generateMetadata({ params }: { params: Promise<{ driverId: string }> }) {
  try {
    const { data } = await readDriver((await params).driverId);
    return { title: data?.full_name ?? "Driver" };
  } catch {
    return { title: "Driver" };
  }
}
