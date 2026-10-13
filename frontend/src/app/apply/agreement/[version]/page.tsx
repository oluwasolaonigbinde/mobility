import Link from "next/link";
import { notFound } from "next/navigation";
import { DRIVER_AGREEMENTS } from "@/lib/driver-agreement";

export default async function AgreementPage({ params }: { params: Promise<{ version: string }> }) {
  const { version } = await params;
  const sections = Object.hasOwn(DRIVER_AGREEMENTS, version)
    ? DRIVER_AGREEMENTS[version]
    : undefined;
  if (!sections) notFound();
  return (
    <main className="mx-auto max-w-2xl px-5 py-10">
      <Link href="/apply" className="text-cyan text-sm underline">
        Apply to drive
      </Link>
      <h1 className="font-display mt-6 text-3xl font-semibold">Driver agreement</h1>
      <p className="text-muted mt-2 text-sm">Terrax Media · Version {version}</p>
      {sections.map((section) => (
        <section key={section.title} className="mt-7">
          <h2 className="text-lg font-semibold">{section.title}</h2>
          <p className="mt-2 leading-relaxed">{section.text}</p>
        </section>
      ))}
    </main>
  );
}
