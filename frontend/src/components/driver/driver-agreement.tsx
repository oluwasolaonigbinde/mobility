import Link from "next/link";
import { DRIVER_AGREEMENT_POINTS, DRIVER_AGREEMENT_VERSION } from "@/lib/driver-agreement";

export function DriverAgreement() {
  return (
    <section className="border-edge rounded-xl border p-4" aria-label="Driver agreement">
      <h3 className="font-semibold">Driver agreement</h3>
      <ul className="my-3 list-disc space-y-2 pl-5 text-sm">
        {DRIVER_AGREEMENT_POINTS.map((point) => (
          <li key={point}>{point}</li>
        ))}
      </ul>
      <Link
        href={`/apply/agreement/${DRIVER_AGREEMENT_VERSION}`}
        target="_blank"
        rel="noreferrer"
        className="text-cyan text-sm underline"
      >
        Read the full agreement
      </Link>
      <input type="hidden" name="agreement_version" value={DRIVER_AGREEMENT_VERSION} />
      <label className="mt-4 flex items-center gap-3 text-sm">
        <input type="checkbox" name="agreement_accepted" required className="h-5 w-5" />I agree
      </label>
    </section>
  );
}
