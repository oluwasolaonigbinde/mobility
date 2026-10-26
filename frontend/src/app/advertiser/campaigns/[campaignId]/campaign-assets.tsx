import Link from "next/link";
import type { ApiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { loadAdvertiserPageData } from "@/lib/advertiser/page-data";
import { previewFile } from "@/lib/advertiser/campaign-visuals";
import { formatDate } from "@/lib/format";
import { CampaignArtwork } from "@/components/campaigns/campaign-artwork";
import { VanPreview } from "@/components/brand/van-preview";
import { PortalIcon } from "@/components/brand/portal-icon";
import { RaiseComplaintForm } from "@/components/complaints/forms";
import { raiseAdvertiserComplaintAction } from "@/lib/complaints/actions";
import { CreativeStatusActions } from "./creative-status-actions";
import { ArtworkWebsite } from "./artwork-website";

type Creative = components["schemas"]["CreativeRead"];
const labels: Record<string, string> = {
  approved: "Approved",
  pending_review: "Waiting for approval",
  rejected: "Rejected",
  draft: "Waiting to be sent",
  ready: "Upload this artwork again",
  archived: "Archived",
};

export async function CampaignAssets({
  api,
  campaignId,
  campaignName,
  items,
  canWrite,
  locked,
  changeAvailable,
  available,
  reasons,
}: {
  api: ApiClient;
  campaignId: string;
  campaignName: string;
  items: Creative[];
  canWrite: boolean;
  locked: boolean;
  changeAvailable: boolean;
  available: boolean;
  reasons: Map<string, string | undefined>;
}) {
  const current =
    items.find((item) => item.status === "approved") ??
    items.find((item) => item.status !== "archived");
  const file = previewFile(current ? [current] : []);
  const isPDF = current?.mime_type === "application/pdf";
  const metadataFile = current?.asset_source === "managed_file" ? current.stored_file_id : null;
  const openFile = current?.scan_status === "clean" ? metadataFile : null;
  const storedFile = metadataFile
    ? await loadAdvertiserPageData(() =>
        api.GET("/api/v1/advertiser/files/{file_id}", {
          params: { path: { file_id: metadataFile } },
        }),
      )
    : null;
  const fileDetails =
    storedFile?.available && storedFile.data.id === metadataFile ? storedFile.data : null;
  const websites = await Promise.all(
    items
      .filter((item) => item.status !== "archived")
      .map(async (item) => {
        const result = await loadAdvertiserPageData(() =>
          api.GET("/api/v1/advertiser/campaigns/{campaign_id}/creatives/{creative_id}/website", {
            params: { path: { campaign_id: campaignId, creative_id: item.id } },
          }),
        );
        const metadataId = item.asset_source === "managed_file" ? item.stored_file_id : null;
        const itemFileId = item.scan_status === "clean" ? metadataId : null;
        const detail =
          item.id === current?.id
            ? storedFile
            : metadataId
              ? await loadAdvertiserPageData(() =>
                  api.GET("/api/v1/advertiser/files/{file_id}", {
                    params: { path: { file_id: metadataId } },
                  }),
                )
              : null;
        const uploadedFile =
          detail?.available && detail.data.id === metadataId ? detail.data : null;
        return { item, result, uploadedFile, itemFileId };
      }),
  );
  return (
    <details className="brand-disclosure mb-6" open id="campaign-assets">
      <summary>
        Campaign assets{" "}
        <span className="text-muted mr-5 ml-auto hidden text-sm font-normal sm:inline">
          Artwork and QR code
        </span>
      </summary>
      <div className="border-edge border-t p-5 md:p-6">
        {!available ? (
          <p className="text-muted">
            Artwork couldn&apos;t be loaded.{" "}
            <Link href={`/advertiser/campaigns/${campaignId}`} className="underline">
              Try again
            </Link>
          </p>
        ) : (
          <>
            <div className="grid gap-6 lg:grid-cols-2">
              <section>
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                  <h2 className="font-semibold">Your advert</h2>
                  {canWrite && changeAvailable && !locked ? (
                    <a
                      href={`/advertiser/campaigns/new?campaignId=${campaignId}`}
                      className="text-green text-sm font-semibold"
                    >
                      {current ? "Replace artwork" : "Upload artwork"}
                    </a>
                  ) : null}
                </div>
                <div className="border-edge h-48 overflow-hidden rounded-xl border bg-[#f5f0e5]">
                  {current && !file ? (
                    <div className="flex h-full flex-col items-center justify-center gap-3 p-5 text-center">
                      <PortalIcon name="bill" className="text-green size-10" />
                      <p className="font-semibold">
                        {fileDetails?.original_filename ?? current.name}
                      </p>
                      {openFile ? (
                        <a
                          href={`/api/advertiser/artwork/${openFile}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="brand-secondary"
                        >
                          Open artwork
                        </a>
                      ) : (
                        <p className="text-muted text-sm">Artwork file</p>
                      )}
                    </div>
                  ) : (
                    <CampaignArtwork
                      name={campaignName}
                      fileId={file}
                      className="object-contain p-5"
                    />
                  )}
                </div>
                {current ? (
                  <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
                    <span
                      className={`rounded-full px-3 py-1 font-semibold ${current.status === "approved" ? "text-green bg-[#e3f4dd]" : current.status === "rejected" ? "text-coral bg-[#fde4e6]" : "bg-[#fdf3d3] text-[#7a5230]"}`}
                    >
                      {labels[current.status] ?? "Waiting"}
                    </span>
                    <span className="text-muted">
                      {fileDetails
                        ? `Uploaded ${formatDate(fileDetails.created_at)}`
                        : "Upload date unavailable"}
                    </span>
                  </div>
                ) : (
                  <p className="text-muted mt-3 text-sm">
                    Upload your design to see it on the car.
                  </p>
                )}
                {current?.status === "rejected" ? (
                  <p className="text-coral mt-3 text-sm">
                    {reasons.get(current.id) ??
                      "The rejection reason couldn't be loaded. Refresh to try again."}
                  </p>
                ) : null}
              </section>
              <section>
                <h2 className="mb-3 font-semibold">See it on a car</h2>
                <div className="border-edge h-48 overflow-hidden rounded-xl border">
                  <VanPreview
                    source={file ? `/api/advertiser/artwork/${file}` : null}
                    label="Preview of your advert on a car"
                  />
                </div>
                <p className="text-muted mt-3 text-sm">
                  {isPDF
                    ? "Preview shows image files"
                    : current && !file
                      ? "Your artwork preview is not available yet."
                      : "A preview of the design. Terrax Media checks the fit before printing."}
                </p>
                {isPDF ? <p className="sr-only">PDF artwork</p> : null}
              </section>
            </div>
            {canWrite && !changeAvailable ? (
              <p className="text-muted mt-4 text-sm">
                Artwork changes couldn&apos;t be checked.{" "}
                <Link href={`/advertiser/campaigns/${campaignId}`} className="underline">
                  Refresh to try again
                </Link>
                .
              </p>
            ) : null}
            {locked && canWrite ? (
              <details className="border-edge bg-raised mt-5 rounded-xl border p-4">
                <summary className="cursor-pointer font-semibold">Ask Terrax to change it</summary>
                <div id="artwork-change">
                  <p className="text-muted mt-3 mb-4 text-sm">
                    This campaign&apos;s artwork is locked. Ask Terrax to change it. New artwork
                    means reprinting and refitting each car.
                  </p>
                  <RaiseComplaintForm
                    party="advertiser"
                    action={raiseAdvertiserComplaintAction}
                    references={{
                      campaigns: [{ id: campaignId, label: campaignName }],
                      trips: [],
                      payouts: [],
                    }}
                    initialCategory="campaign_or_job"
                    initialReference={`campaign:${campaignId}`}
                  />
                </div>
              </details>
            ) : null}
            {websites.map(({ item, result, uploadedFile, itemFileId }) => (
              <section key={item.id} className="border-edge mt-5 border-t pt-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-4">
                    <div className="border-edge h-20 w-28 shrink-0 overflow-hidden rounded-lg border bg-[#f5f0e5]">
                      {previewFile([item]) ? (
                        <CampaignArtwork
                          name={item.name}
                          fileId={previewFile([item])}
                          className="h-full w-full object-contain p-2"
                        />
                      ) : (
                        <div className="text-green flex h-full flex-col items-center justify-center gap-1 text-xs">
                          <PortalIcon name="bill" className="size-6" />
                          <span>
                            {item.mime_type === "application/pdf" ? "PDF artwork" : "Artwork file"}
                          </span>
                        </div>
                      )}
                    </div>
                    <div className="min-w-0">
                      <h3 className="font-semibold">
                        {item.mime_type === "application/pdf"
                          ? (uploadedFile?.original_filename ?? item.name)
                          : item.name}
                      </h3>
                      <p className="text-muted mt-1 text-sm">
                        <span
                          className={`inline-block rounded-full px-2 py-0.5 font-semibold ${item.status === "approved" ? "text-green bg-[#e3f4dd]" : item.status === "rejected" ? "text-coral bg-[#fde4e6]" : "bg-[#fdf3d3] text-[#7a5230]"}`}
                        >
                          {labels[item.status]}
                        </span>
                        {" · "}
                        {uploadedFile
                          ? `Uploaded ${formatDate(uploadedFile.created_at)}`
                          : "Upload date unavailable"}
                      </p>
                      {itemFileId && !previewFile([item]) ? (
                        <a
                          href={`/api/advertiser/artwork/${itemFileId}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-green mt-2 inline-block text-sm font-semibold"
                          aria-label={`Open ${item.name}`}
                        >
                          Open artwork
                        </a>
                      ) : null}
                      {item.status === "rejected" ? (
                        <p className="text-coral mt-2 text-sm">
                          {reasons.get(item.id) ??
                            "The feedback couldn't be loaded. Refresh to try again."}
                        </p>
                      ) : null}
                    </div>
                  </div>
                  {canWrite && changeAvailable && !locked ? (
                    <CreativeStatusActions
                      campaignId={campaignId}
                      creativeId={item.id}
                      status={item.status}
                    />
                  ) : null}
                </div>
                {result.available && result.data.creative_id === item.id ? (
                  <ArtworkWebsite
                    campaignId={campaignId}
                    creativeId={item.id}
                    destination={result.data.destination}
                    linked={Boolean(result.data.short_path)}
                    scans={result.data.scans}
                    canWrite={canWrite}
                  />
                ) : (
                  <p className="text-muted mt-4 text-sm">
                    Website link and QR code couldn&apos;t be loaded.{" "}
                    <Link href={`/advertiser/campaigns/${campaignId}`} className="underline">
                      Try again
                    </Link>
                  </p>
                )}
              </section>
            ))}
          </>
        )}
      </div>
    </details>
  );
}
