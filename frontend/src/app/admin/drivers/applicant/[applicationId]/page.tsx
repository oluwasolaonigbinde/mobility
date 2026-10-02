import DriverHub, { type DriverHubQuery } from "../../driver-hub";
export default async function ApplicantPage({
  params,
  searchParams,
}: {
  params: Promise<{ applicationId: string }>;
  searchParams: Promise<DriverHubQuery>;
}) {
  return <DriverHub applicationId={(await params).applicationId} query={await searchParams} />;
}
