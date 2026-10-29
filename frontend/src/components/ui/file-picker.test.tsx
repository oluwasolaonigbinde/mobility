import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { FilePicker } from "./file-picker";

it("keeps the selected File for the upload caller and clears removal and form reset", async () => {
  const onFile = vi.fn();
  const { container } = render(
    <form>
      <FilePicker name="document" label="Licence" onFile={onFile} />
    </form>,
  );
  const input = screen.getByLabelText("Licence") as HTMLInputElement;
  const file = new File(["licence"], "licence.pdf", { type: "application/pdf" });
  await userEvent.upload(input, file);
  expect(input.files?.[0]).toBe(file);
  expect(onFile).toHaveBeenLastCalledWith(file);
  expect(screen.getByText("licence.pdf")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Replace" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Remove" }));
  expect(input.files).toHaveLength(0);
  expect(onFile).toHaveBeenLastCalledWith(undefined);
  await userEvent.upload(input, file);
  fireEvent.reset(container.querySelector("form")!);
  expect(screen.queryByText("licence.pdf")).not.toBeInTheDocument();
});

it("wraps a long file name instead of cutting it to a few characters on a phone", async () => {
  render(<FilePicker name="document" label="Registration papers" />);
  const name = "vehicle-registration-certificate-2026-scan-front.pdf";
  await userEvent.upload(
    screen.getByLabelText("Registration papers"),
    new File(["papers"], name, { type: "application/pdf" }),
  );
  const shown = screen.getByText(name);
  expect(shown).toHaveAttribute("title", name);
  // The name may wrap onto two lines; the buttons drop below it on a narrow card.
  expect(shown).not.toHaveClass("truncate");
  expect(shown).toHaveClass("line-clamp-2", "[overflow-wrap:anywhere]");
  expect(shown.parentElement).toHaveClass("min-w-0", "basis-40");
  expect(shown.parentElement?.parentElement).toHaveClass("flex-wrap");
});

it("shows upload progress and failure without discarding the selection", async () => {
  const { rerender } = render(<FilePicker name="document" label="Licence" />);
  const file = new File(["licence"], "licence.pdf", { type: "application/pdf" });
  await userEvent.upload(screen.getByLabelText("Licence"), file);
  rerender(<FilePicker name="document" label="Licence" state="uploading" disabled />);
  expect(screen.getByText("Uploading…")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Replace" })).toBeDisabled();
  rerender(<FilePicker name="document" label="Licence" state="failed" error="Please try again" />);
  expect(screen.getByText("Upload failed")).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("Please try again");
  expect(screen.getByText("licence.pdf")).toBeInTheDocument();
  rerender(<FilePicker name="document" label="Licence" state="uploaded" />);
  expect(screen.getByText("Uploaded")).toBeInTheDocument();
});
