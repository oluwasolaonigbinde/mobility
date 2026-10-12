import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CarChooser } from "./car-chooser";
import { VehicleForm } from "./vehicle-form";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function renderInForm(code = "") {
  render(
    <form aria-label="car">
      <input name="application_access_token" defaultValue={code} aria-label="code" />
      <CarChooser />
    </form>,
  );
  return screen.getByRole("form", { name: "car" }) as HTMLFormElement;
}

it("lists the applicant's own cars by plate and sends the chosen one as vehicle_id", async () => {
  fetchMock.mockResolvedValue(
    Response.json({
      items: [
        { vehicle_id: "car-1", plate_number: "ABC-123-XY", status: "rejected" },
        { vehicle_id: "car-2", plate_number: "LND-222-ZZ", status: "approved" },
      ],
    }),
  );
  const form = renderInForm("  emailed-code  ");

  fireEvent.click(screen.getByRole("button", { name: "Find my cars" }));

  expect(await screen.findByText("ABC-123-XY")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith("/api/apply/onboarding/vehicles", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ application_access_token: "emailed-code" }),
  });
  expect(screen.getByText("(not approved)")).toBeInTheDocument();
  expect(screen.getByText("(approved)")).toBeInTheDocument();
  expect(new FormData(form).get("vehicle_id")).toBe("");
  fireEvent.click(screen.getByRole("radio", { name: /ABC-123-XY/ }));
  expect(new FormData(form).get("vehicle_id")).toBe("car-1");
  expect(screen.queryByText("car-1")).not.toBeInTheDocument();
});

it("forgets the looked-up cars when the onboarding code is changed", async () => {
  fetchMock.mockResolvedValue(
    Response.json({
      items: [{ vehicle_id: "car-1", plate_number: "ABC-123-XY", status: "approved" }],
    }),
  );
  render(<VehicleForm />);
  fireEvent.change(screen.getByLabelText("Code from your email"), {
    target: { value: "first-code" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Find my cars" }));
  expect(await screen.findByText("ABC-123-XY")).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Code from your email"), {
    target: { value: "second-code" },
  });
  expect(screen.queryByText("ABC-123-XY")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Find my cars" })).toBeInTheDocument();
});

it("asks for the code before looking anything up", async () => {
  renderInForm();
  fireEvent.click(screen.getByRole("button", { name: "Find my cars" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Enter the code from your email first.",
  );
  expect(fetchMock).not.toHaveBeenCalled();
});

it("explains in plain words when the code is not accepted", async () => {
  fetchMock.mockResolvedValue(
    Response.json(
      { error: { code: "ONBOARDING_ACCESS_INVALID", message: "Onboarding access is unavailable" } },
      { status: 404 },
    ),
  );
  renderInForm("expired-code");
  fireEvent.click(screen.getByRole("button", { name: "Find my cars" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "This code doesn't work. It may be mistyped, expired or replaced. Get a new code on the first step.",
  );
  expect(screen.queryByRole("radio")).not.toBeInTheDocument();
});
