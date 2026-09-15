import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef, useState } from "react";
import { expect, it, vi } from "vitest";
import { ConfirmationDialog } from "./confirmation-dialog";

it("uses a modal dialog, handles Escape and restores focus to its trigger", async () => {
  const user = userEvent.setup();
  const confirm = vi.fn();

  function Harness() {
    const [open, setOpen] = useState(false);
    const triggerRef = useRef<HTMLButtonElement>(null);
    return (
      <>
        <button ref={triggerRef} type="button" onClick={() => setOpen(true)}>
          Remove item
        </button>
        <ConfirmationDialog
          open={open}
          onOpenChange={setOpen}
          title="Remove named item?"
          description="This cannot be undone."
          cancelLabel="Keep item"
          confirmLabel="Confirm removal"
          onConfirm={confirm}
          returnFocusRef={triggerRef}
        />
      </>
    );
  }

  render(<Harness />);
  const trigger = screen.getByRole("button", { name: "Remove item" });
  await user.click(trigger);

  const dialog = screen.getByRole("alertdialog");
  expect(dialog.tagName).toBe("DIALOG");
  const cancel = screen.getByRole("button", { name: "Keep item" });
  const remove = screen.getByRole("button", { name: "Confirm removal" });
  expect(cancel).toHaveFocus();
  await user.keyboard("{Shift>}{Tab}{/Shift}");
  expect(remove).toHaveFocus();
  await user.keyboard("{Tab}");
  expect(cancel).toHaveFocus();

  await user.keyboard("{Escape}");

  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
  expect(confirm).not.toHaveBeenCalled();
});
