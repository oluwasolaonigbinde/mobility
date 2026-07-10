import Link from "next/link";
import { Panel } from "@/components/ui/panel";

export default function NotFound() {
  return (
    <main className="bg-atmosphere flex min-h-dvh items-center justify-center p-6">
      <Panel className="w-full max-w-sm p-8 text-center">
        <p className="micro text-amber">404</p>
        <h1 className="font-display mt-2 text-2xl font-semibold">Off the map.</h1>
        <p className="text-muted mt-3 text-sm">
          This page doesn&apos;t exist — or you don&apos;t have access to it.
        </p>
        <Link
          href="/"
          className="bg-amber text-bg hover:bg-amber-soft mt-6 inline-flex h-11 w-full items-center justify-center rounded-lg text-sm font-medium transition-colors"
        >
          Back to your dashboard
        </Link>
      </Panel>
    </main>
  );
}
