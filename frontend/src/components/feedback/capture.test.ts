import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const domToCanvas = vi.hoisted(() => vi.fn());
vi.mock("modern-screenshot", () => ({ domToCanvas }));

import { captureViewport, encode, parkUnloadedOffscreenImages, scrubClone } from "./capture";

type FakeCanvas = HTMLCanvasElement & { toDataURL: ReturnType<typeof vi.fn> };
const jpeg = (bytes: number) => `data:image/jpeg;base64,${"A".repeat(bytes)}`;
function fakeCanvas(width: number, height: number, sizes: number[] = [1000]): FakeCanvas {
  const toDataURL = vi.fn();
  for (const size of sizes) toDataURL.mockReturnValueOnce(jpeg(size));
  return { width, height, toDataURL, getContext: () => ({ drawImage: vi.fn() }) } as never;
}

afterEach(() => vi.restoreAllMocks());

it("hides private regions and the widget and blanks password inputs in the clone", () => {
  const root = document.createElement("div");
  root.innerHTML = `
    <p data-feedback-private>NIN 12345678901</p>
    <section data-feedback-private><input name="account_number" value="0123456789" /></section>
    <div data-feedback-widget><button>Feedback</button></div>
    <input type="password" value="secret" />
    <p id="public">Visible</p>`;
  scrubClone(root);
  for (const node of root.querySelectorAll<HTMLElement>(
    "[data-feedback-private], [data-feedback-widget]",
  ))
    expect(node.style.getPropertyValue("visibility")).toBe("hidden");
  const password = root.querySelector<HTMLInputElement>('input[type="password"]')!;
  expect(password.value).toBe("");
  expect(password.getAttribute("value")).toBe("");
  expect(root.querySelector<HTMLElement>("#public")!.style.visibility).toBe("");
});

/** Adds an image to the page at a position, loaded or not. */
function pageImage(top: number, complete: boolean, attrs: Record<string, string>) {
  const img = document.createElement("img");
  for (const [name, value] of Object.entries(attrs)) img.setAttribute(name, value);
  Object.defineProperty(img, "complete", { value: complete });
  vi.spyOn(img, "getBoundingClientRect").mockReturnValue({
    top,
    bottom: top + 100,
    left: 0,
    right: 200,
  } as DOMRect);
  document.body.append(img);
  return img;
}

describe("parking unloaded off-screen images", () => {
  afterEach(() => document.body.querySelectorAll("img").forEach((img) => img.remove()));

  it("parks only unloaded images outside the viewport, then puts them back exactly", () => {
    const below = pageImage(2540, false, {
      src: "/fleet.svg",
      srcset: "/fleet.svg 1x",
      loading: "lazy",
    });
    const above = pageImage(-400, false, { src: "/above.png" });
    const loadedBelow = pageImage(3000, true, { src: "/loaded.png" });
    const loadingOnScreen = pageImage(100, false, { src: "/hero.png" });
    const noSrcset = pageImage(5958, false, { src: "/logo.png" });
    const srcsetOnly = pageImage(4000, false, { srcset: "/wide.png 2x" });

    const restore = parkUnloadedOffscreenImages(1280, 800);
    expect(below.hasAttribute("src")).toBe(false);
    expect(below.hasAttribute("srcset")).toBe(false);
    expect(above.hasAttribute("src")).toBe(false);
    expect(noSrcset.hasAttribute("src")).toBe(false);
    expect(loadedBelow.getAttribute("src")).toBe("/loaded.png");
    expect(loadingOnScreen.getAttribute("src")).toBe("/hero.png");

    restore();
    expect(below.getAttribute("src")).toBe("/fleet.svg");
    expect(below.getAttribute("srcset")).toBe("/fleet.svg 1x");
    expect(above.getAttribute("src")).toBe("/above.png");
    expect(noSrcset.getAttribute("src")).toBe("/logo.png");
    expect(noSrcset.hasAttribute("srcset")).toBe(false);
    expect(srcsetOnly.getAttribute("srcset")).toBe("/wide.png 2x");
    expect(srcsetOnly.hasAttribute("src")).toBe(false);
  });

  it("puts parked images back even when the capture fails", async () => {
    vi.spyOn(window, "innerWidth", "get").mockReturnValue(390);
    vi.spyOn(window, "innerHeight", "get").mockReturnValue(844);
    const lazy = pageImage(2540, false, { src: "/fleet.svg" });
    domToCanvas.mockReset().mockImplementation(async () => {
      expect(lazy.hasAttribute("src")).toBe(false);
      throw new Error("blocked");
    });
    await expect(captureViewport()).rejects.toThrow("blocked");
    expect(lazy.getAttribute("src")).toBe("/fleet.svg");
  });
});

it("encodes a narrow canvas as JPEG at the first quality that fits", () => {
  const canvas = fakeCanvas(1170, 2532, [1000]);
  expect(encode(canvas)).toBe(jpeg(1000));
  expect(canvas.toDataURL).toHaveBeenCalledWith("image/jpeg", 0.8);
});

it("downscales a wide canvas to 1200 px and steps quality down until it fits", () => {
  const scaled = fakeCanvas(0, 0, [1_000_000, 950_000, 10_000]);
  const create = vi.spyOn(document, "createElement").mockReturnValue(scaled);
  const source = fakeCanvas(2400, 1500);
  expect(encode(source)).toBe(jpeg(10_000));
  expect(create).toHaveBeenCalledWith("canvas");
  expect([scaled.width, scaled.height]).toEqual([1200, 750]);
  expect(scaled.toDataURL.mock.calls.map((call) => call[1])).toEqual([0.8, 0.65, 0.5]);
  expect(source.toDataURL).not.toHaveBeenCalled();
});

it("refuses a screenshot that stays too large at the lowest quality", () => {
  const canvas = fakeCanvas(800, 600, [1e6, 1e6, 1e6, 1e6]);
  expect(() => encode(canvas)).toThrow("Screenshot is too large");
});

describe("captureViewport", () => {
  beforeEach(() => {
    vi.spyOn(window, "innerWidth", "get").mockReturnValue(390);
    vi.spyOn(window, "innerHeight", "get").mockReturnValue(844);
    vi.spyOn(window, "scrollY", "get").mockReturnValue(250);
    vi.spyOn(window, "devicePixelRatio", "get").mockReturnValue(3);
    domToCanvas.mockReset().mockResolvedValue(fakeCanvas(1170, 2532, [5000]));
  });

  it("captures the visible viewport without fonts, scrubbing the clone", async () => {
    expect(await captureViewport()).toBe(jpeg(5000));
    const [node, options] = domToCanvas.mock.calls[0]!;
    expect(node).toBe(document.body);
    expect(options).toMatchObject({
      width: 390,
      height: 844,
      scale: 3,
      font: false,
      timeout: 5000,
      style: { marginTop: "-250px", marginLeft: "0px" },
    });
    expect(options.filter).toBeUndefined();
    const clone = document.createElement("div");
    clone.innerHTML = '<input type="password" value="pw" /><p data-feedback-private>x</p>';
    options.onCloneNode(clone);
    expect(clone.querySelector("input")!.value).toBe("");
    expect(clone.querySelector("p")!.style.visibility).toBe("hidden");
    options.onCloneNode(document.createTextNode("ignored"));
  });

  it("caps the scale so a desktop capture is at most 1200 px wide", async () => {
    vi.spyOn(window, "innerWidth", "get").mockReturnValue(1600);
    vi.spyOn(window, "devicePixelRatio", "get").mockReturnValue(2);
    domToCanvas.mockResolvedValue(fakeCanvas(1200, 600, [5000]));
    await captureViewport();
    expect(domToCanvas.mock.calls[0]![1].scale).toBe(0.75);
  });

  it("passes a capture failure to the caller", async () => {
    domToCanvas.mockRejectedValue(new Error("blocked"));
    await expect(captureViewport()).rejects.toThrow("blocked");
  });
});
