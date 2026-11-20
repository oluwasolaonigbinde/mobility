import { expect, it } from "vitest";
import { feedbackTitle, portalLabel, safePagePath } from "./page-label";

it("labels portals and falls back to Public", () => {
  expect(portalLabel("advertiser")).toBe("Advertiser");
  expect(portalLabel("staff")).toBe("Staff");
  expect(portalLabel("other")).toBe("Public");
});

it.each([
  "//evil.example",
  "/\\evil.example",
  "https://evil.example",
  "/a?b=1",
  "/a#x",
  "/a\u0000b",
  "relative",
])("refuses an off-site or unsafe page path: %s", (path) => expect(safePagePath(path)).toBeNull());

it("keeps same-site paths", () => expect(safePagePath("/driver/track")).toBe("/driver/track"));

it("uses the first sentence as the title and keeps it short", () => {
  expect(feedbackTitle("The button is hidden. Also the map is slow.")).toBe(
    "The button is hidden.",
  );
  expect(feedbackTitle("No full stop here")).toBe("No full stop here");
  expect(feedbackTitle("x".repeat(200))).toHaveLength(118);
});
