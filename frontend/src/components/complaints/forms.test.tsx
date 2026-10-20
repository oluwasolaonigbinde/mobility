import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ComplaintMessageForm, ComplaintUpdateForm, RaiseComplaintForm } from "./forms";

vi.mock("@/lib/complaints/actions", () => ({}));

describe("complaint forms", () => {
  it("raises with a category, optional record and message, and shows errors", async () => {
    const user = userEvent.setup();
    const action = vi.fn(async (_state: unknown, data: FormData) => {
      expect(data.get("category")).toBe("pay_or_payout");
      expect(data.get("reference")).toBe("campaign:j1");
      expect(String(data.get("client_request_id"))).toMatch(/[0-9a-f-]{36}/);
      return { error: "We couldn't find that record in your account." };
    });
    render(
      <RaiseComplaintForm
        party="driver"
        action={action}
        references={{
          campaigns: [{ id: "j1", label: "Wuse lunch rush" }],
          trips: [{ id: "t1", label: "Trip on 3 Sep" }],
          payouts: [{ id: "p1", label: "Trip pay ₦10" }],
        }}
      />,
    );

    const categories = screen.getByLabelText("What is it about?");
    expect(
      Array.from((categories as HTMLSelectElement).options).map((o) => o.textContent),
    ).not.toContain("Billing or invoices");
    await user.selectOptions(categories, "pay_or_payout");
    const record = screen.getByLabelText("Which job is this about? (optional)");
    expect(screen.getByRole("group", { name: "Jobs" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Trip on 3 Sep" })).toBeNull();
    expect(screen.queryByRole("option", { name: "Trip pay ₦10" })).toBeNull();
    await user.selectOptions(record, "campaign:j1");
    await user.type(screen.getByLabelText("Tell us what happened"), "Paid short");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("couldn't find that record");
    expect(action).toHaveBeenCalledTimes(1);
  });

  it("offers advertisers only campaigns", () => {
    render(
      <RaiseComplaintForm
        party="advertiser"
        action={vi.fn()}
        references={{ campaigns: [{ id: "c1", label: "Launch" }], trips: [], payouts: [] }}
      />,
    );
    expect(screen.getByLabelText("Which campaign is this about? (optional)")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Campaigns" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Billing or invoices" })).toBeInTheDocument();
  });

  it("sends a staff reply with the resolve choice and shows success", async () => {
    const user = userEvent.setup();
    const action = vi.fn(async (_state: unknown, data: FormData) => {
      expect(data.get("resolve")).toBe("on");
      expect(data.get("complaint_id")).toBe("c1");
      return { done: "Reply sent and conversation resolved." };
    });
    render(
      <ComplaintMessageForm
        complaintId="c1"
        action={action}
        label="Reply as Terrax Media"
        placeholder="…"
        submitLabel="Send reply"
        allowResolve
      />,
    );
    await user.type(screen.getByLabelText("Reply as Terrax Media"), "Done");
    await user.click(screen.getByLabelText("Mark as resolved with this reply"));
    await user.click(screen.getByRole("button", { name: "Send reply" }));
    expect(await screen.findByText(/Reply sent and conversation resolved/)).toBeInTheDocument();
  });

  it("does not submit an empty message", async () => {
    const user = userEvent.setup();
    const action = vi.fn();
    render(
      <ComplaintMessageForm
        complaintId="c1"
        action={action}
        label="Add a message"
        placeholder="…"
        submitLabel="Send message"
      />,
    );
    expect(screen.queryByLabelText(/Mark as resolved/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(action).not.toHaveBeenCalled();
  });

  it("saves the complaint status", async () => {
    const user = userEvent.setup();
    const action = vi.fn(async (_state: unknown, data: FormData) => {
      expect(data.get("status")).toBe("resolved");
      expect(data.has("assignee")).toBe(false);
      return { done: "Saved." };
    });
    render(<ComplaintUpdateForm complaintId="c1" action={action} />);
    await user.selectOptions(screen.getByLabelText("Status"), "resolved");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.getByText(/Saved\./)).toBeInTheDocument());
  });
});

describe("message form after a successful send", () => {
  it("keeps the confirmation and uses a fresh request id for the next message", async () => {
    const user = userEvent.setup();
    const ids: string[] = [];
    const action = vi.fn(async (_state: unknown, data: FormData) => {
      ids.push(String(data.get("client_request_id")));
      return { done: "Sent. Customer Service will reply here." };
    });
    render(
      <ComplaintMessageForm
        complaintId="c1"
        action={action}
        label="Add a message"
        placeholder="…"
        submitLabel="Send message"
      />,
    );
    await user.type(screen.getByLabelText("Add a message"), "First");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(await screen.findByText(/Customer Service will reply here/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Add a message")).toHaveValue(""));
    await user.type(screen.getByLabelText("Add a message"), "Second");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() => expect(ids).toHaveLength(2));
    expect(ids[0]).not.toBe(ids[1]);
  });
});

describe("retrying after a failed send", () => {
  it("reuses the same request id so the server can recognise the retry", async () => {
    const user = userEvent.setup();
    const ids: string[] = [];
    const action = vi.fn(async (_state: unknown, data: FormData) => {
      ids.push(String(data.get("client_request_id")));
      return ids.length === 1
        ? { error: "Cardvert couldn't send this right now." }
        : { done: "Sent." };
    });
    render(
      <ComplaintMessageForm
        complaintId="c1"
        action={action}
        label="Add a message"
        placeholder="…"
        submitLabel="Send message"
      />,
    );
    await user.type(screen.getByLabelText("Add a message"), "Hello");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByRole("alert");
    await user.clear(screen.getByLabelText("Add a message"));
    await user.type(screen.getByLabelText("Add a message"), "Hello");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByText(/Sent\./);
    expect(ids).toHaveLength(2);
    expect(ids[0]).toBe(ids[1]);
  });
});
