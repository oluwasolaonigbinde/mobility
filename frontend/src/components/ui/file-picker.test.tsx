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
