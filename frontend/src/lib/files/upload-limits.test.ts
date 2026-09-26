import { afterEach, describe, expect, it, vi } from "vitest";
import { uploadInstallationImage } from "./installation-evidence-upload";
import { uploadOnboardingFile } from "./onboarding-upload";

const MB = 1024 * 1024;

function sized(name: string, type: string, bytes: number): File {
  const file = new File(["x"], name, { type });
  Object.defineProperty(file, "size", { value: bytes });
  return file;
}

describe("per-purpose upload limits before any request (client answer #12)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("refuses identity documents over 10 MB and vehicle files over 20 MB", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    await expect(
      uploadOnboardingFile(
        "token",
        sized("id.pdf", "application/pdf", 10 * MB + 1),
        "r1",
        "driver_kyc",
      ),
    ).rejects.toThrow("Identity documents must be no bigger than 10 MB.");
    await expect(
      uploadOnboardingFile(
        "token",
        sized("papers.pdf", "application/pdf", 20 * MB + 1),
        "r2",
        "vehicle_evidence",
      ),
    ).rejects.toThrow("Vehicle documents and photos must be no bigger than 20 MB.");
    await expect(
      uploadOnboardingFile("token", sized("clip.mp4", "video/mp4", MB), "r3", "driver_kyc"),
    ).rejects.toThrow("Choose a PDF, JPEG, PNG or WebP file.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("refuses installation photos over 20 MB", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    await expect(
      uploadInstallationImage(sized("front.jpg", "image/jpeg", 20 * MB + 1)),
    ).rejects.toThrow("Choose a photo that is no bigger than 20 MB.");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
