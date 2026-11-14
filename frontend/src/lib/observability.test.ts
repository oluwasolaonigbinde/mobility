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

  it("redacts link tokens in relative navigation breadcrumbs", () => {
    const scrubbed = scrubSentryEvent({
      breadcrumbs: [
        {
          category: "navigation",
          data: {
            from: "/apply#application_access_token=live-secret",
            to: "/reset-password?token=reset-secret&next=1",
          },
        },
      ],
    });

    expect(JSON.stringify(scrubbed)).not.toMatch(/live-secret|reset-secret/);
    expect(scrubbed.breadcrumbs[0]!.data).toEqual({
      from: "/apply#application_access_token=[REDACTED_TOKEN]",
      to: "/reset-password?token=[REDACTED_TOKEN]&next=1",
    });
  });

  it("redacts free-text emails and phone numbers in messages and exceptions", () => {
    const scrubbed = scrubSentryEvent({
      message: "Invite failed for Ada.Obi+test@example.co.uk, call +234 803 555 0101",
      exception: {
        values: [
          { value: "Driver 08035550101 (or 0803-555-0102, +447700900101) not reachable" },
          { value: "Fallback +1 (415) 555-0199 and +234-803-555-0103" },
        ],
      },
      breadcrumbs: [{ message: "contact: someone@cardvert.example" }],
    });

    const text = JSON.stringify(scrubbed);
    expect(text).not.toMatch(/example\.co\.uk|cardvert\.example|555|0101|900101/);
    expect(scrubbed.message).toBe("Invite failed for [REDACTED_EMAIL], call [REDACTED_PHONE]");
    expect(scrubbed.exception.values[0]!.value).toBe(
      "Driver [REDACTED_PHONE] (or [REDACTED_PHONE], [REDACTED_PHONE]) not reachable",
    );
    expect(scrubbed.exception.values[1]!.value).toBe(
      "Fallback [REDACTED_PHONE] and [REDACTED_PHONE]",
    );
    expect(scrubbed.breadcrumbs[0]!.message).toBe("contact: [REDACTED_EMAIL]");
  });

  it("keeps correlation ids, dates, UUIDs and amounts readable", () => {
    const kept = {
      request_id: "edge-request-123",
      release_revision: "0a1b2c3d".repeat(5),
      message:
        "Report 00000000-0000-4000-8000-000000000001 on 2026-08-24T12:00:00Z for NGN 1,250,000.00 (12345 trips)",
    };
    expect(scrubSentryEvent(kept)).toEqual(kept);
  });
});
