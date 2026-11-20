import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  path: "/advertiser",
  prefill: vi.fn(),
  capture: vi.fn(),
}));
vi.mock("next/navigation", () => ({ usePathname: () => mocks.path }));
vi.mock("./actions", () => ({ feedbackNamePrefill: mocks.prefill }));
vi.mock("./capture", () => ({ captureViewport: mocks.capture }));

import { FeedbackWidget } from "./feedback-widget";

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_FEEDBACK_ENABLED", "1");
  mocks.path = "/advertiser";
  mocks.prefill.mockReset().mockResolvedValue("Ada Advertiser");
  mocks.capture.mockReset().mockResolvedValue("data:image/jpeg;base64,AAAA");
  fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "received" })));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

const sentCall = () => fetchMock.mock.calls[0] as [string, RequestInit];
const sentBody = () => JSON.parse(sentCall()[1].body as string);

it("renders nothing unless the build flag is 1, and nothing on the review page", () => {
  vi.stubEnv("NEXT_PUBLIC_FEEDBACK_ENABLED", "");
  const { container, rerender } = render(<FeedbackWidget />);
  expect(container).toBeEmptyDOMElement();
  vi.stubEnv("NEXT_PUBLIC_FEEDBACK_ENABLED", "1");
  mocks.path = "/feedback";
  rerender(<FeedbackWidget />);
  expect(screen.queryByRole("button", { name: "Feedback" })).toBeNull();
});

it("prefills the signed-in name, sends a text note, and returns focus on close", async () => {
  const user = userEvent.setup({ delay: null });
  render(<FeedbackWidget />);
  await user.click(screen.getByRole("button", { name: "Feedback" }));
  const dialog = screen.getByRole("dialog", { name: "Send feedback" });
  expect(dialog).toBeInTheDocument();
  await waitFor(() => expect(screen.getByLabelText("Your name")).toHaveValue("Ada Advertiser"));
  expect(screen.getByLabelText("Current page")).toHaveValue("/advertiser");
  await user.type(screen.getByLabelText("Feedback"), "The chart is hard to read.");
  await user.click(screen.getByRole("button", { name: "Send feedback" }));
  expect(await screen.findByText("Thanks — feedback sent")).toBeInTheDocument();
  expect(sentCall()[0]).toBe("/api/feedback");
  expect(sentBody()).toEqual({
    name: "Ada Advertiser",
    page_path: "/advertiser",
    message: "The chart is hard to read.",
    website: null,
    screenshot: null,
  });
  await user.click(screen.getByRole("button", { name: "Close" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Feedback" })).toHaveFocus());
});

it("requires a name and feedback before sending", async () => {
  mocks.prefill.mockResolvedValue("");
  const user = userEvent.setup({ delay: null });
  render(<FeedbackWidget />);
  await user.click(screen.getByRole("button", { name: "Feedback" }));
  await user.click(screen.getByRole("button", { name: "Send feedback" }));
  expect(screen.getByText("Enter your name")).toBeInTheDocument();
  expect(screen.getByText("Enter your feedback")).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});

it("marks an area with a tap, sends the pin as fractions, and can remove the mark", async () => {
  const user = userEvent.setup({ delay: null });
  render(<FeedbackWidget />);
  await user.click(screen.getByRole("button", { name: "Feedback" }));
  await user.type(screen.getByLabelText("Feedback"), "Wrong total.");
  await user.click(screen.getByRole("button", { name: "Mark area" }));
  const overlay = screen.getByRole("application");
  await act(async () => {
    overlay.dispatchEvent(
      new MouseEvent("click", {
        bubbles: true,
        clientX: window.innerWidth / 2,
        clientY: window.innerHeight / 4,
      }),
    );
  });
  expect(await screen.findByRole("button", { name: "Remove mark" })).toBeInTheDocument();
  expect(screen.getByAltText("Marked screenshot")).toHaveAttribute(
    "src",
    "data:image/jpeg;base64,AAAA",
  );
  await user.click(screen.getByRole("button", { name: "Send feedback" }));
  await screen.findByText("Thanks — feedback sent");
  expect(sentBody().screenshot).toEqual({
    data_url: "data:image/jpeg;base64,AAAA",
    pin_x: 0.5,
    pin_y: 0.25,
  });
});

it("blocks taps with a visible label while capturing, and files the note under the marked page", async () => {
  let finish!: (value: string) => void;
  mocks.capture.mockReturnValue(new Promise<string>((resolve) => (finish = resolve)));
  const user = userEvent.setup({ delay: null });
  const { rerender } = render(<FeedbackWidget />);
  await user.click(screen.getByRole("button", { name: "Feedback" }));
  await user.type(screen.getByLabelText("Feedback"), "Wrong total.");
  await user.click(screen.getByRole("button", { name: "Mark area" }));
  await act(async () => {
    screen.getByRole("application").dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  const layer = await screen.findByTestId("feedback-capturing");
  expect(layer).toHaveClass("fixed", "inset-0");
  expect(layer.closest("[data-feedback-widget]")).not.toBeNull();
  expect(screen.getByRole("status")).toHaveTextContent("Capturing the screen…");
  expect(screen.queryByRole("dialog")).toBeNull();
  mocks.path = "/advertiser/billing";
  rerender(<FeedbackWidget />);
  await act(async () => finish("data:image/jpeg;base64,BBBB"));
  expect(await screen.findByRole("button", { name: "Remove mark" })).toBeInTheDocument();
  expect(screen.queryByTestId("feedback-capturing")).toBeNull();
  expect(screen.getByLabelText("Current page")).toHaveValue("/advertiser");
  await user.click(screen.getByRole("button", { name: "Send feedback" }));
  await screen.findByText("Thanks — feedback sent");
  expect(sentBody().page_path).toBe("/advertiser");
});

it("Escape cancels marking, and a failed capture falls back to text only", async () => {
  mocks.capture.mockRejectedValue(new Error("blocked"));
  const user = userEvent.setup({ delay: null });
  render(<FeedbackWidget />);
  await user.click(screen.getByRole("button", { name: "Feedback" }));
  await user.click(screen.getByRole("button", { name: "Mark area" }));
  await user.keyboard("{Escape}");
  expect(screen.getByRole("dialog", { name: "Send feedback" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Mark area" }));
  await act(async () => {
    screen.getByRole("application").dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  expect(
    await screen.findByText(
      "We couldn't capture the screen. You can still send your feedback without it.",
    ),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Mark area" })).toBeInTheDocument();
});

it("shows rate-limit copy and keeps the note", async () => {
  fetchMock.mockResolvedValue(new Response("{}", { status: 429 }));
  const user = userEvent.setup({ delay: null });
  render(<FeedbackWidget />);
  await user.click(screen.getByRole("button", { name: "Feedback" }));
  await user.type(screen.getByLabelText("Feedback"), "Hello.");
  await user.click(screen.getByRole("button", { name: "Send feedback" }));
  expect(
    await screen.findByText("You've sent a lot of feedback. Try again in a few minutes."),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Feedback")).toHaveValue("Hello.");
});

it("sits above the driver tab bar and lifts the panel above an on-screen keyboard", async () => {
  mocks.path = "/driver";
  const listeners: Record<string, () => void> = {};
  const viewport = {
    height: 844,
    offsetTop: 0,
    addEventListener: (t: string, f: () => void) => (listeners[t] = f),
    removeEventListener: vi.fn(),
  };
  vi.stubGlobal("visualViewport", viewport);
  vi.spyOn(window, "innerHeight", "get").mockReturnValue(844);
  const user = userEvent.setup({ delay: null });
  render(<FeedbackWidget />);
  expect(screen.getByRole("button", { name: "Feedback" }).style.bottom).toContain("5rem");
  await user.click(screen.getByRole("button", { name: "Feedback" }));
  viewport.height = 500;
  act(() => listeners.resize?.());
  const dialog = screen.getByRole("dialog", { name: "Send feedback" });
  expect(dialog.style.bottom).toBe("352px");
  expect(dialog.style.maxHeight).toBe("484px");
});
