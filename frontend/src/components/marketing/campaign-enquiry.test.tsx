import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ submit: vi.fn() }));
vi.mock("@/app/campaign-enquiry-actions", () => ({ submitCampaignEnquiry: mocks.submit }));
import { CampaignEnquiry } from "./campaign-enquiry";

async function fill() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Company"), "Test brand");
  await user.type(screen.getByLabelText("Contact name"), "Test contact");
  await user.type(screen.getByLabelText("Email address"), "contact@example.test");
  await user.type(screen.getByLabelText("Tell us about your campaign"), "Abuja next month");
  return user;
}

describe("campaign enquiry form", () => {
  beforeEach(() => vi.clearAllMocks());
  it("provides required labelled fields, limits and an email alternative", () => {
    render(<CampaignEnquiry />);
    expect(screen.getByLabelText("Company")).toBeRequired();
    expect(screen.getByLabelText("Tell us about your campaign")).toHaveAttribute(
      "maxlength",
      "2000",
    );
    expect(screen.getByLabelText("Phone number (optional)")).not.toBeRequired();
    expect(screen.getByRole("link", { name: "terraxmediacompany@gmail.com" })).toHaveAttribute(
      "href",
      "mailto:terraxmediacompany@gmail.com",
    );
  });
  it("shows pending, disables submission, then replaces the form after success", async () => {
    let resolve!: (value: { submitted: boolean }) => void;
    mocks.submit.mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    render(<CampaignEnquiry />);
    const user = await fill();
    await user.click(screen.getByRole("button", { name: "Send enquiry" }));
    expect(screen.getByRole("button", { name: "Sending enquiry…" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("Sending your enquiry");
    await act(async () => resolve({ submitted: true }));
    expect(screen.getByRole("status")).toHaveTextContent("Your enquiry has been sent");
    expect(screen.queryByRole("button", { name: "Send enquiry" })).not.toBeInTheDocument();
  });
  it("retains values after a failure and allows retry", async () => {
    mocks.submit
      .mockResolvedValueOnce({
        error: "Could not send",
        values: {
          company: "Test brand",
          contact_name: "Test contact",
          email: "contact@example.test",
          brief: "Abuja next month",
        },
      })
      .mockResolvedValueOnce({ submitted: true });
    render(<CampaignEnquiry />);
    const user = await fill();
    await user.click(screen.getByRole("button", { name: "Send enquiry" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not send");
    expect(screen.getByLabelText("Company")).toHaveValue("Test brand");
    await user.click(screen.getByRole("button", { name: "Send enquiry" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Your enquiry has been sent");
  });
  it("associates server field errors with their inputs", async () => {
    mocks.submit.mockResolvedValue({
      fieldErrors: { company: "Enter this detail" },
      values: { company: "Test brand" },
    });
    render(<CampaignEnquiry />);
    const user = await fill();
    await user.click(screen.getByRole("button", { name: "Send enquiry" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter this detail");
    expect(screen.getByLabelText("Company")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Company")).toHaveAttribute(
      "aria-describedby",
      "enquiry-company-error",
    );
  });
});
