import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { JobArtwork } from "./job-artwork";
it("uses only the private same-origin artwork route and keeps the fallback until bytes load", () => {
  const { container } = render(
    <JobArtwork assignmentId="assignment" kind="image" compact={false} />,
  );
  expect(screen.getByRole("img", { name: /Illustration/ })).toBeInTheDocument();
  const preview = container.querySelector<HTMLImageElement>(
    'img[src="/api/driver/jobs/assignment/artwork"]',
  )!;
  expect(preview).not.toBeNull();
  expect(preview).toHaveAttribute("loading", "lazy");
  fireEvent.load(preview);
  expect(screen.getByRole("img", { name: "Advert for this job" })).toHaveAttribute(
    "src",
    "/api/driver/jobs/assignment/artwork",
  );
  expect(screen.queryByRole("img", { name: /Illustration/ })).toBeNull();
});
it("removes a denied or failed image and keeps the local illustration", () => {
  const { container } = render(
    <JobArtwork assignmentId="assignment" kind="image" compact={false} />,
  );
  fireEvent.error(container.querySelector('img[src^="/api/driver/"]')!);
  expect(container.querySelector('img[src^="/api/driver/"]')).toBeNull();
  expect(screen.getByRole("img", { name: /Illustration/ })).toBeInTheDocument();
});
it.each(["document", "video"] as const)(
  "opens %s through the authorised route on demand",
  (kind) => {
    const { container } = render(
      <JobArtwork assignmentId="assignment" kind={kind} compact={false} />,
    );
    const link = screen.getByRole("link", { name: "Open this job’s advert" });
    expect(link).toHaveAttribute("href", "/api/driver/jobs/assignment/artwork");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(container.querySelector('img[src^="/api/driver/"]')).toBeNull();
  },
);
it("does not fetch or link artwork without an authoritative live assignment", () => {
  const { container } = render(<JobArtwork kind="image" compact={false} />);
  expect(container.querySelector('img[src^="/api/driver/"]')).toBeNull();
  expect(screen.queryByRole("link")).toBeNull();
});
