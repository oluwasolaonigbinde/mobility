"use client";
import { useRouter } from "next/navigation";
import { SearchSelect } from "../search-select";
export function DriverPicker({ section }: { section: string }) {
  const router = useRouter();
  return (
    <SearchSelect
      kind="driver_any"
      name="driver"
      label="Driver"
      onSelect={(id) => router.push(`/admin/drivers/${id}#${section}`)}
    />
  );
}
