/**
 * Viewport screenshot for the feedback widget (REQ-336). Runs only in the browser and loads
 * the capture library on demand, so pages pay nothing until someone marks an area.
 */

export const MAX_SCREENSHOT_WIDTH = 1200;
const MAX_DATA_URL_BYTES = 900 * 1024;
const PRIVATE_SELECTOR = "[data-feedback-private], [data-feedback-widget]";

/** Hide the widget and private regions (layout kept) and blank password fields in a clone. */
export function scrubClone(root: ParentNode): void {
  root.querySelectorAll<HTMLElement>(PRIVATE_SELECTOR).forEach((node) => {
    node.style.setProperty("visibility", "hidden", "important");
  });
  root.querySelectorAll<HTMLInputElement>('input[type="password"]').forEach((input) => {
    input.value = "";
    input.setAttribute("value", "");
  });
}

const MEDIA_TAGS = new Set(["IMG", "PICTURE", "VIDEO", "IFRAME", "CANVAS"]);

/**
 * Leave out media wholly below or right of the viewport. The library otherwise fetches every
 * image on the page to inline it, including lazy images that have never loaded; dropping them
 * can't move anything on screen because they sit after the visible area.
 */
export function keepNode(node: Node, width: number, height: number): boolean {
  if (!(node instanceof Element) || !MEDIA_TAGS.has(node.tagName)) return true;
  const box = node.getBoundingClientRect();
  return box.top < height && box.left < width;
}

export function encode(canvas: HTMLCanvasElement): string {
  let width = canvas.width;
  let source = canvas;
  if (width > MAX_SCREENSHOT_WIDTH) {
    const scaled = document.createElement("canvas");
    scaled.width = MAX_SCREENSHOT_WIDTH;
    scaled.height = Math.round((canvas.height * MAX_SCREENSHOT_WIDTH) / width);
    scaled.getContext("2d")?.drawImage(canvas, 0, 0, scaled.width, scaled.height);
    source = scaled;
    width = scaled.width;
  }
  for (const quality of [0.8, 0.65, 0.5, 0.35]) {
    const dataUrl = source.toDataURL("image/jpeg", quality);
    if (dataUrl.startsWith("data:image/jpeg") && dataUrl.length <= MAX_DATA_URL_BYTES)
      return dataUrl;
  }
  throw new Error("Screenshot is too large");
}

/** Capture what is currently on screen as a JPEG data URL no wider than 1200 px. */
export async function captureViewport(): Promise<string> {
  const width = window.innerWidth;
  const height = window.innerHeight;
  const scale = Math.min(window.devicePixelRatio || 1, MAX_SCREENSHOT_WIDTH / width);
  const background = getComputedStyle(document.body).backgroundColor || "#ffffff";
  const { domToCanvas } = await import("modern-screenshot");
  const scrollX = window.scrollX;
  const scrollY = window.scrollY;
  const canvas = await domToCanvas(document.body, {
    width,
    height,
    scale,
    backgroundColor: background,
    timeout: 15000,
    // Web-font embedding builds a <style> element, which the site CSP (style-src 'self')
    // blocks. The screenshot falls back to system fonts instead.
    font: false,
    // The sandboxed clone starts at the page top; shift the flow content to the viewport.
    // Fixed elements (the driver tab bar) stay put because margins don't move them.
    style: {
      marginTop: `${-scrollY}px`,
      marginLeft: `${-scrollX}px`,
      minHeight: "0",
    },
    filter: (node) => keepNode(node, width, height),
    onCloneNode: (cloned) => {
      if (cloned instanceof Element) scrubClone(cloned);
    },
  });
  return encode(canvas);
}
