import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { CampaignArtwork } from "./campaign-artwork";
it("replaces denied or missing artwork with a local illustration", () => {
  render(<CampaignArtwork name="Marula" fileId="file-1" />);
  const image = screen.getByRole("img", { name: "Marula artwork" });
  const preview = new URL(image.getAttribute("src")!, document.baseURI);
  expect(preview.origin).toBe(new URL(document.baseURI).origin);
  expect(preview.pathname).toBe("/api/advertiser/artwork/file-1");
  fireEvent.error(image);
  const fallback = screen.getByRole("img", { name: /Illustration of a car/ });
  expect(new URL(fallback.getAttribute("src")!, document.baseURI).pathname).toBe(
    "/marketing/terrax/hero-vehicle-placeholder.svg",
  );
});
