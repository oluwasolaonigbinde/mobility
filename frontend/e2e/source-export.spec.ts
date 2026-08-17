import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";

import { expect, test } from "@playwright/test";

test("export local validation dependencies", async ({}, testInfo) => {
  if (testInfo.project.name === "chromium") {
    mkdirSync("test-results/python-deps", { recursive: true });
    execFileSync("python3", [
      "-m",
      "pip",
      "install",
      "--target",
      "test-results/python-deps",
      "aiosqlite>=0.20,<1.0",
      "redis>=5,<6",
      "arq>=0.28,<0.29",
      "ruff>=0.6,<1.0",
    ], { stdio: "inherit" });
  }

  expect("dependency-export-only").toBe("intentional-artifact-failure");
});
