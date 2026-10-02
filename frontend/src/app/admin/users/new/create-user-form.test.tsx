import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

const create = vi.hoisted(() => vi.fn());
vi.mock("../actions", () => ({ createUserAction: create }));
import { CreateUserForm } from "./create-user-form";
beforeEach(() => {
  create.mockClear();
  create.mockResolvedValue({ error: "Creation rejected" });
});
it("keeps a staff grant fixed to staff and requires the acting staff password", () => {
  render(<CreateUserForm fixedRole="admin" />);
  expect(screen.queryByRole("radio")).toBeNull();
  expect(document.querySelector('input[name="role"]')).toHaveValue("admin");
  expect(screen.getByLabelText(/Your current password/)).toHaveAttribute("type", "password");
  expect(screen.queryByLabelText("Company name")).toBeNull();
});
it("keeps a company login fixed to advertiser without asking for staff grant proof", () => {
  render(<CreateUserForm fixedRole="advertiser" />);
  expect(screen.queryByRole("radio")).toBeNull();
  expect(document.querySelector('input[name="role"]')).toHaveValue("advertiser");
  expect(screen.queryByLabelText(/Your current password/)).toBeNull();
  expect(screen.getByLabelText("Company name")).toBeRequired();
});

it("locks the created login and retries company creation without another password", async () => {
  const user = userEvent.setup();
  const partial = {
    error: "Retry the company below",
    createdUserId: "00000000-0000-4000-8000-00000000000a",
    createdEmail: "created@example.com",
    createdFullName: "Created advertiser",
    createdPhone: null,
  };
  create.mockResolvedValue(partial);
  render(<CreateUserForm fixedRole="advertiser" />);
  await user.type(screen.getByLabelText("Temporary password"), "temporary-secret-password");
  await user.click(screen.getByRole("button", { name: "Create account" }));
  await screen.findByRole("button", { name: "Retry company creation" });
  expect(screen.getByLabelText("Full name")).toHaveValue(partial.createdFullName);
  expect(screen.getByLabelText("Full name")).toHaveAttribute("readonly");
  expect(screen.getByLabelText("Email")).toHaveAttribute("readonly");
  expect(screen.getByLabelText("Temporary password")).toBeDisabled();
  expect(screen.getByLabelText("Temporary password")).toHaveValue("");
  await user.click(screen.getByRole("button", { name: "Retry company creation" }));
  expect(create.mock.calls[1]![0]).toEqual(partial);
  expect(create.mock.calls[1]![1].get("password")).toBeNull();
  expect(create.mock.calls[1]![1].get("role")).toBe("advertiser");
});

it("asks for masked acting-admin proof only for an admin grant and clears it after failure", async () => {
  const user = userEvent.setup();
  render(<CreateUserForm />);
  expect(screen.queryByLabelText(/Your current password/)).not.toBeInTheDocument();
  await user.click(screen.getByRole("radio", { name: /Terrax staff/ }));
  const proof = screen.getByLabelText(/Your current password/);
  expect(proof).toHaveAttribute("type", "password");
  expect(proof).toBeRequired();
  await user.type(proof, "acting-admin-secret");
  await user.click(screen.getByRole("button", { name: "Create account" }));
  await screen.findByRole("alert");
  expect(create).toHaveBeenCalledOnce();
  const form = create.mock.calls[0] as unknown as [unknown, FormData];
  expect(form[1].get("current_password")).toBe("acting-admin-secret");
  await waitFor(() => expect(proof).toHaveValue(""));
  await user.click(screen.getByRole("radio", { name: /Driver/ }));
  expect(screen.queryByLabelText(/Your current password/)).not.toBeInTheDocument();
});
