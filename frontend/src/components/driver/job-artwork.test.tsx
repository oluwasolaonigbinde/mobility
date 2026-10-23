import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { JobArtwork } from "./job-artwork";
it("fits only the private same-origin artwork onto the approved van", () => {
  const { container } = render(
    <JobArtwork assignmentId="assignment" kind="image" compact={false} />,
  );
  expect(screen.getByRole("img", { name: "Advert for this job on a car" })).toBeInTheDocument();
  const preview = container.querySelector('svg image[href="/api/driver/jobs/assignment/artwork"]');
  expect(preview).not.toBeNull();
  expect(preview).toHaveAttribute("preserveAspectRatio", "xMidYMid slice");
  expect(container.querySelector('image[href="/portal/van-scene.svg"]')).not.toBeNull();
  expect(container.querySelector("img")).toBeNull();
});
it("removes a denied or failed image and keeps the local illustration", () => {
  const { container } = render(
    <JobArtwork assignmentId="assignment" kind="image" compact={false} />,
  );
  fireEvent.error(container.querySelector('image[href^="/api/driver/"]')!);
  expect(container.querySelector('image[href^="/api/driver/"]')).toBeNull();
  expect(screen.getByRole("img", { name: "Artwork preview unavailable" })).toBeInTheDocument();
  expect(container.querySelector('image[href="/portal/van-scene.svg"]')).not.toBeNull();
});
it("opens PDF artwork through the authorized route with an honest neutral preview", () => {
  const { container } = render(
    <JobArtwork assignmentId="assignment" kind="document" compact={false} />,
  );
  const link = screen.getByRole("link", { name: "Open this job’s advert" });
  expect(link).toHaveAttribute("href", "/api/driver/jobs/assignment/artwork");
  expect(link).toHaveAttribute("rel", "noopener noreferrer");
  expect(container.querySelector('image[href^="/api/driver/"]')).toBeNull();
  expect(screen.getByText("Preview shows image files")).toBeInTheDocument();
});
it("does not fetch or link artwork without an authoritative live assignment", () => {
  const { container } = render(<JobArtwork kind="image" compact={false} />);
  expect(container.querySelector('image[href^="/api/driver/"]')).toBeNull();
  expect(screen.queryByRole("link")).toBeNull();
});
