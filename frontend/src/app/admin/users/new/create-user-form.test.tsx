import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

const create = vi.hoisted(() => vi.fn(async () => ({ error: "Creation rejected" })));
vi.mock("../actions", () => ({ createUserAction: create }));
import { CreateUserForm } from "./create-user-form";

it("asks for masked acting-admin proof only for an admin grant and clears it after failure", async () => {
  const user = userEvent.setup();
  render(<CreateUserForm />);
  expect(screen.queryByLabelText(/Your current password/)).not.toBeInTheDocument();
  await user.click(screen.getByRole("radio", { name: /Admin \/ Ops/ }));
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
