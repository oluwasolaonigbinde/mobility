import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SearchSelect } from "./search-select";
const search = vi.hoisted(() => vi.fn());
const preview = vi.hoisted(() => vi.fn());
vi.mock("./queue-options", () => ({
  searchOperatorOptions: search,
  previewOperatorArtwork: preview,
}));
const CAMPAIGN = "11111111-1111-4111-8111-111111111111";
const FILE = "33333333-3333-4333-8333-333333333333";
beforeEach(() => {
  search.mockReset();
  preview.mockReset();
});
afterEach(() => vi.useRealTimers());

async function clickWhenEnabled(
  user: { click: (element: Element) => Promise<void> },
  name: string | RegExp,
) {
  const button = await screen.findByRole("button", { name });
  await vi.waitFor(() => expect(button).toBeEnabled());
  await user.click(button);
}

it("reaches options beyond one hundred and requires explicit available selection", async () => {
  const user = userEvent.setup();
  search.mockImplementation(async ({ offset }) => ({
    total: 101,
    items: [
      { id: `item-${offset}`, label: `Person ${offset}`, detail: "email@example.test" },
      {
        id: "blocked",
        label: "Suspended person",
        detail: "Unavailable",
        unavailable: "Approval required",
      },
    ],
  }));
  const { container } = render(
    <SearchSelect kind="driver" name="driver_profile_id" label="Driver" />,
  );
  await user.click(screen.getByRole("button", { name: "Find driver" }));
  expect(container.querySelector('input[type="hidden"]')).toHaveValue("");
  expect(await screen.findByRole("button", { name: /Suspended person/ })).toBeDisabled();
  for (let i = 0; i < 4; i++) await clickWhenEnabled(user, "Next");
  expect(search).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 100 }));
  await user.click(await screen.findByRole("button", { name: /Person 100/ }));
  expect(container.querySelector('input[type="hidden"]')).toHaveValue("item-100");
});

describe("SearchSelect behaviour", () => {
  it("sends the typed query, pages back, and reports the chosen option", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    search.mockImplementation(async ({ offset }) => ({
      total: 30,
      items: [{ id: `vehicle-${offset}`, label: `Plate ${offset}`, detail: "Toyota · active" }],
    }));
    render(
      <SearchSelect
        kind="vehicle"
        name="vehicle_id"
        label="Vehicle"
        parentId="driver-1"
        onSelect={onSelect}
      />,
    );
    await user.type(screen.getByRole("textbox", { name: "Search Vehicle" }), "ABC");
    await user.click(screen.getByRole("button", { name: "Find vehicle" }));
    expect(search).toHaveBeenCalledWith({
      kind: "vehicle",
      q: "ABC",
      offset: 0,
      parentId: "driver-1",
    });
    expect(await screen.findByText(/30 results · Final eligibility is rechecked/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    await clickWhenEnabled(user, "Next");
    expect(await screen.findByRole("button", { name: /Plate 25/ })).toBeVisible();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    await clickWhenEnabled(user, "Previous");
    expect(await screen.findByRole("button", { name: /Plate 0/ })).toBeVisible();
    expect(search).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 0 }));
    await clickWhenEnabled(user, /Plate 0/);
    expect(onSelect).toHaveBeenCalledWith("vehicle-0");
    expect(screen.getByText("Selected: Plate 0 · Toyota · active")).toBeVisible();
  });

  it("shows an unavailable list as an error instead of an empty result", async () => {
    const user = userEvent.setup();
    search.mockResolvedValue({
      items: [],
      total: 0,
      error: "Selection list is unavailable. Try again.",
    });
    render(<SearchSelect kind="campaign" name="campaign_id" label="Campaign" />);
    await user.click(screen.getByRole("button", { name: "Find campaign" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Selection list is unavailable");
    expect(screen.queryByText(/results ·/)).toBeNull();
  });

  it("blocks a second search while one is still loading", async () => {
    let answer!: (value: unknown) => void;
    search.mockImplementationOnce(() => new Promise((resolve) => (answer = resolve)));
    render(<SearchSelect kind="campaign" name="campaign_id" label="Campaign" />);
    fireEvent.click(screen.getByRole("button", { name: "Find campaign" }));
    const loading = await screen.findByRole("button", { name: "Loading…" });
    expect(loading).toBeDisabled();
    fireEvent.click(loading);
    expect(search).toHaveBeenCalledTimes(1);
    await act(async () => {
      answer({ total: 1, items: [{ id: "c1", label: "Only campaign", detail: "approved" }] });
    });
    expect(await screen.findByRole("button", { name: /Only campaign/ })).toBeEnabled();
  });

  it("uses a controlled value for creatives without a free-text search", async () => {
    const { container } = render(
      <SearchSelect
        kind="creative"
        name="creative_id"
        label="Artwork"
        parentId={CAMPAIGN}
        value="controlled-id"
      />,
    );
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(container.querySelector('input[name="creative_id"]')).toHaveValue("controlled-id");
  });

  it("previews selected artwork on request and removes the temporary link after a minute", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    search.mockResolvedValue({
      total: 1,
      items: [{ id: "creative-1", label: "Rear art", detail: "approved", fileId: FILE }],
    });
    preview.mockResolvedValue({ url: "https://files.example.test/art.png" });
    render(<SearchSelect kind="creative" name="creative_id" label="Artwork" parentId={CAMPAIGN} />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Find artwork" })));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: /Rear art/ })));
    expect(preview).not.toHaveBeenCalled();
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "Preview selected artwork" })),
    );
    expect(preview).toHaveBeenCalledWith(FILE);
    expect(screen.getByRole("img", { name: "Selected campaign artwork" })).toHaveAttribute(
      "src",
      "https://files.example.test/art.png",
    );
    act(() => vi.advanceTimersByTime(60_000));
    expect(screen.queryByRole("img", { name: "Selected campaign artwork" })).toBeNull();
  });

  it("explains an unavailable artwork preview", async () => {
    const user = userEvent.setup();
    search.mockResolvedValue({
      total: 1,
      items: [{ id: "creative-1", label: "Rear art", detail: "approved", fileId: FILE }],
    });
    preview.mockResolvedValue({ error: "Artwork preview is unavailable." });
    render(<SearchSelect kind="creative" name="creative_id" label="Artwork" parentId={CAMPAIGN} />);
    await user.click(screen.getByRole("button", { name: "Find artwork" }));
    await user.click(await screen.findByRole("button", { name: /Rear art/ }));
    await clickWhenEnabled(user, "Preview selected artwork");
    expect(await screen.findByRole("alert")).toHaveTextContent("Artwork preview is unavailable.");
    expect(screen.queryByRole("img")).toBeNull();
  });
});
