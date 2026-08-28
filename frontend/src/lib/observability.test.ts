import { describe, expect, it } from "vitest";
import { scrubSentryEvent } from "./observability";

describe("scrubSentryEvent", () => {
  it("removes request identity and private evidence while retaining correlation", () => {
    const scrubbed = scrubSentryEvent({
      request_id: "edge-request-123",
      release_revision: "a".repeat(40),
      request: {
        url: "https://cardvert.example.com/report?token=private",
        headers: { authorization: "Bearer eyJprivate" },
      },
      user: { email: "private@example.invalid" },
      breadcrumbs: [
        {
          message: "artifact=https://objects.example/private lat=9.0765 lon=7.3986",
          data: { fraud_evidence: "raw-private-evidence" },
        },
      ],
    });

    expect(scrubbed.request_id).toBe("edge-request-123");
    expect(scrubbed.release_revision).toBe("a".repeat(40));
    expect(scrubbed).not.toHaveProperty("request");
    expect(scrubbed).not.toHaveProperty("user");
    expect(JSON.stringify(scrubbed)).not.toContain("raw-private-evidence");
    expect(JSON.stringify(scrubbed)).not.toContain("objects.example");
    expect(JSON.stringify(scrubbed)).not.toContain("9.0765");
  });
});
