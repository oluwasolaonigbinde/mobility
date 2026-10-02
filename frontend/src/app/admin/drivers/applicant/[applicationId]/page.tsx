import { readApplication } from "../../../entity-reads";
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

export async function generateMetadata({ params }: { params: Promise<{ applicationId: string }> }) {
  try {
    const { data } = await readApplication((await params).applicationId);
    return { title: data?.full_name ?? "Driver" };
  } catch {
    return { title: "Driver" };
  }
}
