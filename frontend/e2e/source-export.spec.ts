import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";

import { expect, test } from "@playwright/test";

test("export pinned source snapshot for isolated implementation", async ({}, testInfo) => {
  if (testInfo.project.name === "chromium") {
    mkdirSync("test-results", { recursive: true });
    execFileSync("tar", [
      "-czf",
      "test-results/mobility-source.tar.gz",
      "-C",
      "..",
      "AGENTS.md",
      "agent.md",
      "alembic",
      "alembic.ini",
      "app",
      "docker-compose.yml",
      "docker-compose.production.yml",
      "frontend/AGENTS.md",
      "frontend/e2e",
      "frontend/package.json",
      "frontend/package-lock.json",
      "frontend/playwright.config.ts",
      "frontend/src",
      "frontend/tsconfig.json",
      "openapi.json",
      "pyproject.toml",
      "scripts",
      "tests",
    ]);
  }

  expect("source-export-only").toBe("intentional-artifact-failure");
});
