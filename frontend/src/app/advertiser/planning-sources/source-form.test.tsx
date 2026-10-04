import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

vi.mock("./actions", () => ({ createSourceAction: vi.fn(async () => ({})) }));
import { SourceForm } from "./source-form";

it("explains the allowed categories without internal approval wording", () => {
  render(<SourceForm />);
  expect(screen.getByText(/Choose categories only/)).toBeInTheDocument();
  expect(
    screen.getByText(/Names, emails, phone numbers, links, notes and files/),
  ).toBeInTheDocument();
  expect(screen.queryByText(/legal basis|approved yet|approval is in place/i)).toBeNull();
});
