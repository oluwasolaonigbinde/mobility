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
