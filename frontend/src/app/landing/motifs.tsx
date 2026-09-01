/**
 * Brand motif, drawn rather than imported.
 *
 * The Terrax Media logo mark is a stylised "T" sitting inside a field of
 * wood-grain contours (Brand Guide, "Logo Construction"). Laid on their side
 * those contours read as routes running across the page, which is what the
 * product actually is — advertising that travels.
 *
 * Decorative and aria-hidden. Geometry is computed from the index alone, so
 * server and client render identical markup.
 */

const SPAN = 1600;
const STEP = 32;

/** One flowing contour running left to right at a given offset. */
function routePath(index: number, spacing: number) {
  const baseY = index * spacing;
  const amp = 10 + ((index * 7) % 14);
  const freq = 0.0035 + (index % 5) * 0.0007;
  const phase = index * 0.87;
  let d = "";
  for (let x = 0; x <= SPAN; x += STEP) {
    const y =
      baseY +
      amp * Math.sin(x * freq + phase) +
      amp * 0.45 * Math.sin(x * freq * 2.4 + phase * 1.7);
    d += `${x === 0 ? "M" : "L"}${x} ${y.toFixed(1)}`;
  }
  return d;
}

export function GrainField({ lines = 14, spacing = 26 }: { lines?: number; spacing?: number }) {
  const height = lines * spacing;
  return (
    <svg
      viewBox={`0 0 ${SPAN} ${height}`}
      preserveAspectRatio="none"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <g stroke="currentColor" strokeWidth={2} strokeLinecap="round">
        {Array.from({ length: lines }, (_, i) => (
          <path key={i} d={routePath(i, spacing)} />
        ))}
      </g>
    </svg>
  );
}
