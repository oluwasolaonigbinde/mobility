import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";

import { expect, test } from "@playwright/test";

test("export pinned source snapshot for isolated implementation", async ({}, testInfo) => {
  if (testInfo.project.name === "chromium") {
    mkdirSync("test-results", { recursive: true });
    execFileSync("tar", [
      "-czf",
      "test-results/mobility-source.tar.gz",
      "--exclude=.git",
      "--exclude=frontend/node_modules",
      "--exclude=frontend/.next",
      "--exclude=frontend/test-results",
      "--exclude=.pytest_cache",
      "--exclude=**/__pycache__",
      "-C",
      "..",
      ".",
    ]);
  }

  expect("source-export-only").toBe("intentional-artifact-failure");
});
