import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const decision = vi.hoisted(() => vi.fn(async () => ({})));

vi.mock("./actions", () => ({ reviewInstallationEvidenceAction: decision }));

import { InstallationReviewActions } from "./installation-review-actions";

const SUBMISSION_ID = "00000000-0000-4000-8000-00000000000f";
const FRONT_ID = "00000000-0000-4000-8000-000000000015";
const REAR_ID = "00000000-0000-4000-8000-000000000016";
const SIGNED_URL = "https://objects.example/private/front.png?X-Amz-Signature=abc";
const photos = [
  { view: "front", stored_file_id: FRONT_ID },
  { view: "rear_left", stored_file_id: REAR_ID },
];

function issued(url = SIGNED_URL) {
  return new Response(JSON.stringify({ url, expires_in_seconds: 60 }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

function image(type = "image/png") {
  return new Response(new Uint8Array([137, 80, 78, 71]), {
    status: 200,
    headers: { "content-type": type },
  });
}

describe("InstallationReviewActions evidence viewer", () => {
  const fetchMock = vi.fn();
  const createObjectURL = vi.fn();
  const revokeObjectURL = vi.fn();
  const open = vi.fn();

  beforeEach(() => {
    let sequence = 0;
    fetchMock.mockReset();
    decision.mockClear();
    createObjectURL.mockReset().mockImplementation(() => `blob:http://localhost/${++sequence}`);
    revokeObjectURL.mockReset();
    open.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("open", open);
    Object.assign(URL, { createObjectURL, revokeObjectURL });
  });

  afterEach(() => vi.unstubAllGlobals());

  async function view(name: string) {
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name }));
    });
  }

  it("shows the audited signed photo inline without a popup or exposing the signed URL", async () => {
    let releaseIssue: (response: Response) => void = () => undefined;
    fetchMock
      .mockImplementationOnce(() => new Promise<Response>((resolve) => (releaseIssue = resolve)))
      .mockResolvedValueOnce(image());
    const { container } = render(
      <InstallationReviewActions submissionId={SUBMISSION_ID} photos={photos} />,
    );

    await view("View front");
    expect(screen.getByRole("button", { name: "Opening…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "View rear left" })).toBeDisabled();

    await act(async () => releaseIssue(issued()));

    const photo = await screen.findByRole("img", { name: "Front installation evidence" });
    expect(photo).toHaveAttribute("src", "blob:http://localhost/1");
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      `/api/admin/files/${FRONT_ID}/installation-review`,
      {
        method: "POST",
      },
    );
    const [storageUrl, storageInit] = fetchMock.mock.calls[1] ?? [];
    expect(storageUrl).toBe(SIGNED_URL);
    expect(storageInit).not.toHaveProperty("headers");
    expect(storageInit).not.toHaveProperty("body");
    expect(storageInit).toMatchObject({ credentials: "omit", referrerPolicy: "no-referrer" });
    expect(open).not.toHaveBeenCalled();
    expect(container.innerHTML).not.toContain("objects.example");
    for (const element of container.querySelectorAll("img")) {
      expect(element.getAttribute("src")).not.toMatch(/^https?:/);
    }
    expect(screen.getByRole("button", { name: "View rear left" })).toBeEnabled();
    expect(decision).not.toHaveBeenCalled();
  });

  it("revokes the displayed photo when replaced, closed and unmounted", async () => {
    fetchMock
      .mockResolvedValueOnce(issued())
      .mockResolvedValueOnce(image())
      .mockResolvedValueOnce(issued())
      .mockResolvedValueOnce(image("image/jpeg"))
      .mockResolvedValueOnce(issued())
      .mockResolvedValueOnce(image("image/webp"));
    const { unmount } = render(
      <InstallationReviewActions submissionId={SUBMISSION_ID} photos={photos} />,
    );

    await view("View front");
    await screen.findByRole("img", { name: "Front installation evidence" });
    await view("View rear left");
    await screen.findByRole("img", { name: "Rear left installation evidence" });
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:http://localhost/1");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Close photo" }));
    });
    expect(screen.queryByRole("img")).toBeNull();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:http://localhost/2");

    await view("View front");
    await screen.findByRole("img", { name: "Front installation evidence" });
    unmount();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:http://localhost/3");
    expect(decision).not.toHaveBeenCalled();
  });

  it.each([
    {
      name: "the server refuses the governed read",
      responses: () => [
        Promise.resolve(
          new Response(
            JSON.stringify({ error: { message: "The private file object is unavailable" } }),
            { status: 409 },
          ),
        ),
      ],
      message: "The private file object is unavailable",
    },
    {
      name: "the server returns a non-JSON failure",
      responses: () => [Promise.resolve(new Response("<html>Bad gateway</html>", { status: 502 }))],
      message: "The evidence photo could not be opened. Try again.",
    },
    {
      name: "the evidence service is unreachable",
      responses: () => [Promise.reject(new TypeError("Failed to fetch"))],
      message: "Could not reach the evidence service. Try again.",
    },
    {
      name: "storage blocks or drops the signed retrieval",
      responses: () => [
        Promise.resolve(issued()),
        Promise.reject(new TypeError("Failed to fetch")),
      ],
      message: "The signed evidence photo could not be retrieved. Try again.",
    },
    {
      name: "the signed URL has expired",
      responses: () => [
        Promise.resolve(issued()),
        Promise.resolve(new Response("AccessDenied", { status: 403 })),
      ],
      message: "The signed evidence photo could not be retrieved. Try again.",
    },
    {
      name: "the object is not an allowed image type",
      responses: () => [Promise.resolve(issued()), Promise.resolve(image("image/svg+xml"))],
      message: "The evidence file is not a viewable image.",
    },
  ])("reports a visible failure when $name", async ({ responses, message }) => {
    for (const response of responses()) fetchMock.mockImplementationOnce(() => response);
    render(<InstallationReviewActions submissionId={SUBMISSION_ID} photos={photos} />);

    await view("View front");

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(message));
    expect(screen.queryByRole("img")).toBeNull();
    expect(createObjectURL).not.toHaveBeenCalled();
    expect(open).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "View front" })).toBeEnabled();
    expect(decision).not.toHaveBeenCalled();
  });
});
