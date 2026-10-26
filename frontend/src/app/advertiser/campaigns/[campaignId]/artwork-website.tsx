"use client";

import { useActionState, useId, useState } from "react";
import Image from "next/image";
import { saveArtworkWebsite, type WebsiteState } from "./website-actions";
import { PortalIcon } from "@/components/brand/portal-icon";

export function ArtworkWebsite({
  campaignId,
  creativeId,
  destination,
  linked,
  canWrite,
  scans,
}: {
  campaignId: string;
  creativeId: string;
  destination: string | null;
  linked: boolean;
  canWrite: boolean;
  scans: number;
}) {
  const [state, action, pending] = useActionState(saveArtworkWebsite, {} as WebsiteState);
  const id = useId();
  const [imageFailed, setImageFailed] = useState(false);
  const qr = `/api/advertiser/campaigns/${campaignId}/creatives/${creativeId}/qr`;
  return (
    <section className="border-edge mt-5 border-t pt-5" aria-label="Website and QR code">
      <h3 className="flex items-center gap-2 font-semibold">
        <PortalIcon name="qr" />
        Website and QR code
      </h3>
      <p className="text-muted mt-2 text-sm">
        People can scan the code on your advert to open this website.
      </p>
      {canWrite ? (
        <form action={action} className="mt-4 grid gap-3">
          <input type="hidden" name="campaign_id" value={campaignId} />
          <input type="hidden" name="creative_id" value={creativeId} />
          <label htmlFor={id} className="text-sm font-medium">
            Website link
          </label>
          <div className="flex flex-wrap gap-3">
            <input
              key={destination ?? "empty"}
              id={id}
              name="destination"
              type="url"
              maxLength={2048}
              required
              placeholder="https://your-website.com"
              defaultValue={destination ?? ""}
              className="border-edge min-h-11 min-w-0 flex-1 rounded-lg border bg-white px-3 text-base"
            />
            <button type="submit" className="brand-secondary" disabled={pending}>
              {pending ? "Saving…" : "Save link"}
            </button>
          </div>
          <p className="text-muted text-xs">
            Use a public https website. Changing the link keeps the same printed QR code.
          </p>
          {state.error ? (
            <p className="text-coral text-sm" role="alert">
              {state.error}
            </p>
          ) : null}
          {state.done ? (
            <p className="text-green text-sm" role="status">
              {state.done}
            </p>
          ) : null}
        </form>
      ) : destination ? (
        <p className="mt-3 text-sm break-all">{destination}</p>
      ) : (
        <p className="text-muted mt-3 text-sm">No website link added yet.</p>
      )}
      {linked ? (
        <div className="mt-4 flex flex-wrap items-center gap-5">
          {!imageFailed ? (
            <Image
              src={qr}
              width={120}
              height={120}
              unoptimized
              alt="QR code for this advert's website"
              className="border-edge rounded-lg border bg-white"
              onError={() => setImageFailed(true)}
            />
          ) : (
            <p className="text-muted text-sm">
              QR preview couldn&apos;t be loaded. Try the download again.
            </p>
          )}
          <div>
            <a href={`${qr}?download=1`} download className="brand-secondary">
              Download QR code
            </a>
            <p className="text-muted mt-3 text-sm">QR scans: {scans.toLocaleString("en-NG")}</p>
            <p className="text-muted mt-1 text-xs">Daily scan totals, without personal data.</p>
          </div>
        </div>
      ) : null}
    </section>
  );
}
