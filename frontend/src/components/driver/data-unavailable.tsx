import Link from "next/link";
import { Panel } from "@/components/ui/panel";

export function DriverDataUnavailable({
  title,
  detail,
  retryHref,
}: {
  title: string;
  detail: string;
  retryHref: string;
}) {
  return (
    <Panel className="p-6" role="alert">
      <p className="micro text-amber">Fresh data unavailable</p>
      <h2 className="mt-2 text-lg font-semibold">{title}</h2>
      <p className="text-muted mt-2 text-sm leading-6">{detail}</p>
      <Link href={retryHref} className="micro text-amber mt-4 inline-block">
        Reconnect and try again →
      </Link>
    </Panel>
  );
}
