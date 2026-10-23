import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { ApiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { CampaignAssets } from "./campaign-assets";
vi.mock("./website-actions", () => ({ saveArtworkWebsite: vi.fn() }));
vi.mock("./creative-status-actions", () => ({
  CreativeStatusActions: () => <input type="file" aria-label="Replace artwork file" />,
}));
vi.mock("@/components/complaints/forms", () => ({
  RaiseComplaintForm: ({ initialReference }: { initialReference: string }) => (
    <form aria-label="Artwork change request">
      <input name="reference" value={initialReference} readOnly />
    </form>
  ),
}));
vi.mock("@/lib/complaints/actions", () => ({ raiseAdvertiserComplaintAction: vi.fn() }));
const creative = {
  id: "art",
  campaign_id: "campaign",
  name: "Brand wrap.png",
  creative_type: "image",
  placement: "vehicle_exterior",
  stored_file_id: "file",
  asset_source: "managed_file",
  scan_status: "clean",
  asset_url: null,
  mime_type: "image/png",
  width_px: 1000,
  height_px: 500,
  duration_seconds: null,
  checksum: null,
  status: "approved",
  metadata: {},
  created_at: "2026-10-20T09:00:00Z",
  updated_at: "2026-10-20T09:00:00Z",
} as components["schemas"]["CreativeRead"];
function props(overrides = {}) {
  const get = vi.fn().mockImplementation(async (path: string) => ({
    data: path.endsWith("/files/{file_id}")
      ? {
          id: "file",
          original_filename: "Actual uploaded file.pdf",
          created_at: "2026-10-20T09:00:00Z",
        }
      : { creative_id: "art", destination: null, short_path: null, scans: 0, days: [] },
  }));
  return {
    api: { GET: get } as unknown as ApiClient,
    campaignId: "campaign",
    campaignName: "Wuse lunch rush",
    items: [creative],
    canWrite: true,
    locked: false,
    changeAvailable: true,
    available: true,
    reasons: new Map<string, string | undefined>(),
    ...overrides,
  };
}
it("shows current image, upload date, approval and the actual artwork on the van", async () => {
  const { container } = render(await CampaignAssets(props()));
  expect(screen.getByRole("link", { name: "Replace artwork" })).toHaveAttribute(
    "href",
    "/advertiser/campaigns/new?campaignId=campaign",
  );
  const artworkURL = new URL(
    screen.getByRole("img", { name: "Wuse lunch rush artwork" }).getAttribute("src")!,
    window.location.href,
  );
  expect(artworkURL.origin).toBe(window.location.origin);
  expect(artworkURL.pathname).toBe("/api/advertiser/artwork/file");
  expect(container.querySelector("svg image[href='/api/advertiser/artwork/file']")).not.toBeNull();
  expect(screen.getAllByText(/Uploaded 20 Oct 2026/).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/Approved/).length).toBeGreaterThan(0);
});
it("uses an honest PDF file tile and neutral preview without a renderer or error", async () => {
  const pdf = {
    ...creative,
    name: "Campaign wrap.pdf",
    creative_type: "pdf",
    mime_type: "application/pdf",
  } as typeof creative;
  const { container } = render(await CampaignAssets(props({ items: [pdf] })));
  expect(screen.getByRole("link", { name: "Open artwork" })).toHaveAttribute(
    "href",
    "/api/advertiser/artwork/file",
  );
  expect(screen.getAllByText("Actual uploaded file.pdf").length).toBeGreaterThan(0);
  expect(screen.getByText("Preview shows image files")).toBeInTheDocument();
  expect(container.querySelector("svg image[href='/api/advertiser/artwork/file']")).toBeNull();
  expect(container.querySelector("canvas")).toBeNull();
  expect(document.body).not.toHaveTextContent(/unavailable|couldn't|failed/i);
});
it("uses the existing campaign-linked support request after production", async () => {
  const { container } = render(await CampaignAssets(props({ locked: true })));
  expect(screen.getAllByText("Ask Terrax to change it")).toHaveLength(1);
  expect(document.body).toHaveTextContent(
    "This campaign's artwork is locked. Ask Terrax to change it.",
  );
  expect(screen.queryByRole("link", { name: "Ask Terrax to change it" })).toBeNull();
  expect(screen.queryByRole("link", { name: "Replace artwork" })).toBeNull();
  expect(container.querySelector("input[type='file']")).toBeNull();
  expect(container.querySelector("form input[name='reference']")).toHaveValue("campaign:campaign");
});
it("does not infer production state from a failed authority read", async () => {
  render(await CampaignAssets(props({ changeAvailable: false })));
  expect(screen.getByText(/Artwork changes couldn't be checked/)).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Replace artwork" })).toBeNull();
  expect(screen.queryByRole("link", { name: "Ask Terrax to change it" })).toBeNull();
});
it("preserves the actual rejection reason, or a truthful reason-read failure", async () => {
  render(
    await CampaignAssets(
      props({
        items: [{ ...creative, status: "rejected" }],
        reasons: new Map([["art", "Use a higher resolution design."]]),
      }),
    ),
  );
  expect(screen.getAllByText("Use a higher resolution design.").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Rejected").length).toBeGreaterThan(0);
});
it("gives every additional artwork its own private thumbnail and actual upload date", async () => {
  const second = {
    ...creative,
    id: "second",
    name: "Door panel — teal",
    stored_file_id: "second-file",
  };
  const get = vi.fn(
    async (
      path: string,
      options: { params: { path: { file_id?: string; creative_id?: string } } },
    ) => ({
      data: path.endsWith("/files/{file_id}")
        ? {
            id: options.params.path.file_id,
            created_at: "2026-10-19T09:00:00Z",
            original_filename: "Door panel.png",
          }
        : {
            creative_id: options.params.path.creative_id,
            destination: null,
            short_path: null,
            scans: 0,
            days: [],
          },
    }),
  );
  render(
    await CampaignAssets(
      props({ items: [creative, second], api: { GET: get } as unknown as ApiClient }),
    ),
  );
  const image = screen.getByRole("img", { name: "Door panel — teal artwork" });
  expect(new URL(image.getAttribute("src")!, window.location.origin).pathname).toBe(
    "/api/advertiser/artwork/second-file",
  );
  expect(screen.getAllByText(/Uploaded 19 Oct 2026/).length).toBeGreaterThan(0);
});
