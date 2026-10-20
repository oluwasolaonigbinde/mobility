import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
vi.mock("./application-forms", () => ({
  DriverApplicationForms: () => <p>Apply form</p>,
  NewCodePanel: () => <p>New link form</p>,
}));
vi.mock("./person-payee-form", () => ({
  PersonPayeeForm: ({ accessToken }: { accessToken: string }) => <p>Details form {accessToken}</p>,
}));
vi.mock("./vehicle-form", () => ({
  VehicleForm: ({ accessToken, cars }: { accessToken: string; cars: unknown[] }) => (
    <p>
      Car form {accessToken} {cars.length}
    </p>
  ),
}));
const later = () => new Date(Date.now() + 3_600_000).toISOString();
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
async function journey(url: string, step?: string) {
  window.history.replaceState(null, "", url);
  const { ApplicationJourney } = await import("./application-journey");
  return render(<ApplicationJourney requestedStep={step} />);
}
beforeEach(() => {
  vi.resetModules();
});
afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});
it("opens the details step, sending the link only in the request body and storing nothing", async () => {
  const storage = vi.spyOn(Storage.prototype, "setItem");
  const fetch = vi
    .spyOn(window, "fetch")
    .mockResolvedValue(
      json({ step: "details", state: "details_needed", changes_reason: null, expires_at: later() }),
    );
  await journey("/apply?step=details#application_access_token=private-capability", "details");
  expect(await screen.findByText("Details form private-capability")).toBeInTheDocument();
  expect(window.location.href).not.toContain("private-capability");
  expect(fetch).toHaveBeenCalledTimes(1);
  const [path, init] = fetch.mock.calls[0]!;
  expect(path).toBe("/api/apply/onboarding/continue");
  expect(path).not.toContain("private-capability");
  expect(JSON.parse(String(init?.body))).toEqual({
    application_access_token: "private-capability",
  });
  expect(storage).not.toHaveBeenCalled();
});
it("loads the applicant's cars for the car step", async () => {
  vi.spyOn(window, "fetch").mockImplementation(async (path) =>
    String(path).endsWith("/continue")
      ? json({ step: "car", state: "car_needed", changes_reason: null, expires_at: later() })
      : json({ items: [{ vehicle_id: "car", plate_number: "ABC123", status: "submitted" }] }),
  );
  await journey("/apply?step=car#application_access_token=private-capability", "car");
  expect(await screen.findByText("Car form private-capability 1")).toBeInTheDocument();
});
it.each([
  ["details", "details_in_review", "We’re checking your details"],
  ["car", "car_in_review", "We’re checking your car"],
])(
  "shows a waiting message, not a form, while the %s step is in review",
  async (step, state, heading) => {
    const fetch = vi
      .spyOn(window, "fetch")
      .mockResolvedValue(json({ step, state, changes_reason: null, expires_at: later() }));
    await journey(`/apply?step=${step}#application_access_token=waiting`, step);
    expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
    expect(screen.getByText("We’ll email you when we’ve finished.")).toBeInTheDocument();
    expect(screen.queryByText(/Details form|Car form/)).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(1);
  },
);
it("shows the reviewer's reason as given above the form when changes are needed", async () => {
  const reason = "Your ID details do not match. Please check them.";
  vi.spyOn(window, "fetch").mockImplementation(async (path) =>
    String(path).endsWith("/continue")
      ? json({
          step: "car",
          state: "car_changes_needed",
          changes_reason: reason,
          expires_at: later(),
        })
      : json({ items: [] }),
  );
  await journey("/apply?step=car#application_access_token=fix-it", "car");
  expect(await screen.findByText("Car form fix-it 0")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Please make a change" })).toBeInTheDocument();
  expect(screen.getByText(reason)).toBeInTheDocument();
});
it("treats a state that does not match its step as an unavailable link", async () => {
  vi.spyOn(window, "fetch").mockResolvedValue(
    json({ step: "details", state: "car_needed", changes_reason: null, expires_at: later() }),
  );
  await journey("/apply?step=details#application_access_token=odd", "details");
  expect(await screen.findByRole("alert")).toBeInTheDocument();
  expect(screen.queryByText(/Details form|Car form/)).toBeNull();
});
it.each([404, 410])(
  "explains an expired or used link (%s), including where approved drivers should look",
  async (status) => {
    vi.spyOn(window, "fetch").mockResolvedValue(json({ code: "NOT_FOUND" }, status));
    await journey("/apply?step=details#application_access_token=used-link", "details");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This application link isn’t available.",
    );
    expect(
      screen.getByText("If you’ve been approved, check your email for your account set-up link."),
    ).toBeInTheDocument();
    expect(screen.getByText("New link form")).toBeInTheDocument();
    expect(screen.queryByText(/Details form/)).toBeNull();
  },
);
it("fails closed for a forged step without a link, making no request", async () => {
  const fetch = vi.spyOn(window, "fetch");
  await journey("/apply?step=details", "details");
  expect(await screen.findByRole("alert")).toBeInTheDocument();
  expect(screen.queryByText(/Details form/)).toBeNull();
  expect(fetch).not.toHaveBeenCalled();
});
it("shows the normal apply form when no link or step is present", async () => {
  const fetch = vi.spyOn(window, "fetch");
  await journey("/apply");
  expect(await screen.findByText("Apply form")).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});
it("ignores a stale answer once a newer link arrives", async () => {
  let releaseFirst: (response: Response) => void = () => {};
  vi.spyOn(window, "fetch").mockImplementation(async (_path, init) => {
    const token = JSON.parse(String(init?.body)).application_access_token;
    if (token === "first")
      return new Promise<Response>((resolve) => {
        releaseFirst = resolve;
      });
    return json({
      step: "details",
      state: "details_needed",
      changes_reason: null,
      expires_at: later(),
    });
  });
  await journey("/apply?step=details#application_access_token=first", "details");
  await waitFor(() => expect(window.fetch).toHaveBeenCalledTimes(1));
  await act(async () => {
    window.history.replaceState(null, "", "/apply?step=details#application_access_token=second");
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  expect(await screen.findByText("Details form second")).toBeInTheDocument();
  await act(async () =>
    releaseFirst(
      json({ step: "details", state: "details_needed", changes_reason: null, expires_at: later() }),
    ),
  );
  expect(screen.getByText("Details form second")).toBeInTheDocument();
  expect(screen.queryByText(/first/)).toBeNull();
});
it("rejects an answer that has already expired", async () => {
  vi.spyOn(window, "fetch").mockResolvedValue(
    json({
      step: "details",
      state: "details_needed",
      changes_reason: null,
      expires_at: new Date(Date.now() - 1000).toISOString(),
    }),
  );
  await journey("/apply?step=details#application_access_token=old", "details");
  expect(await screen.findByRole("alert")).toBeInTheDocument();
  expect(screen.queryByText(/Details form/)).toBeNull();
});
