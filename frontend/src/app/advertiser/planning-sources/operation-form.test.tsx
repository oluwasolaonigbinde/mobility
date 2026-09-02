import { fireEvent, render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./actions", () => ({
  deactivateSourceAction: vi.fn(async () => ({})),
  removeSourceLinkAction: vi.fn(async () => ({})),
}));

import type { SourceActionState } from "./actions";
import { ensureOperationKey, stableOperationKey } from "./operation-form";

const FIRST_KEY = "00000000-0000-4000-8000-000000000044";
const SECOND_KEY = "00000000-0000-4000-8000-000000000045";

function KeyHarness({ state }: { state: SourceActionState }) {
  const operation = stableOperationKey(state);
  return (
    <form onSubmit={ensureOperationKey}>
      <input key={operation.inputKey} name="operation_key" defaultValue={operation.defaultValue} />
    </form>
  );
}

describe("stable planning operation keys", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("retains a key across retries and rotates only after success", () => {
    vi.spyOn(globalThis.crypto, "randomUUID")
      .mockReturnValueOnce(FIRST_KEY)
      .mockReturnValueOnce(SECOND_KEY);
    const view = render(<KeyHarness state={{}} />);
    const operationInput = () => view.container.querySelector('input[name="operation_key"]');

    expect(operationInput()).toHaveValue("");
    fireEvent.submit(view.container.querySelector("form")!);
    expect(operationInput()).toHaveValue(FIRST_KEY);

    view.rerender(<KeyHarness state={{ error: "response lost", operationKey: FIRST_KEY }} />);
    fireEvent.submit(view.container.querySelector("form")!);
    expect(operationInput()).toHaveValue(FIRST_KEY);

    view.rerender(<KeyHarness state={{ success: "completed", operationKey: FIRST_KEY }} />);
    expect(operationInput()).toHaveValue("");
    fireEvent.submit(view.container.querySelector("form")!);
    expect(operationInput()).toHaveValue(SECOND_KEY);
  });

  it("gives distinct user operations distinct browser keys", () => {
    vi.spyOn(globalThis.crypto, "randomUUID")
      .mockReturnValueOnce(FIRST_KEY)
      .mockReturnValueOnce(SECOND_KEY);
    const first = render(<KeyHarness state={{}} />);
    const second = render(<KeyHarness state={{}} />);

    fireEvent.submit(first.container.querySelector("form")!);
    fireEvent.submit(second.container.querySelector("form")!);
    expect(first.container.querySelector('input[name="operation_key"]')).toHaveValue(FIRST_KEY);
    expect(second.container.querySelector('input[name="operation_key"]')).toHaveValue(SECOND_KEY);
  });
});
