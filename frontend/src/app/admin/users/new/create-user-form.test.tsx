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

it("submits a fixed driver login without changing its role or creating a company", async () => {
  const user = userEvent.setup();
  render(<CreateUserForm fixedRole="driver" />);
  expect(screen.queryByRole("radio")).toBeNull();
  expect(screen.queryByLabelText("Company name")).toBeNull();
  expect(screen.queryByLabelText(/Your current password/)).toBeNull();
  await user.type(screen.getByLabelText("Full name"), "New driver");
  await user.type(screen.getByLabelText("Email"), "new-driver@example.com");
  await user.type(screen.getByLabelText("Temporary password"), "TemporaryDriver123!");
  await user.click(screen.getByRole("button", { name: "Create account" }));
  await screen.findByRole("alert");
  expect(create).toHaveBeenCalledOnce();
  const submitted = create.mock.calls[0]![1] as FormData;
  expect(submitted.get("role")).toBe("driver");
  expect(submitted.get("full_name")).toBe("New driver");
  expect(submitted.get("email")).toBe("new-driver@example.com");
  expect(submitted.get("password")).toBe("TemporaryDriver123!");
  expect(submitted.get("org_name")).toBeNull();
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
it("offers only driver and staff temporary-password accounts", () => {
  render(<CreateUserForm />);
  expect(screen.queryByRole("radio", { name: /Advertiser/ })).toBeNull();
  expect(screen.getAllByRole("radio")).toHaveLength(2);
});
