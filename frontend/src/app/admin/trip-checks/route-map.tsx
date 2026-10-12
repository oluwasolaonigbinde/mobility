import type { components } from "@/lib/api/schema";

type Point = components["schemas"]["AdminTripRoutePointRead"];

const WIDTH = 800;
const HEIGHT = 520;
const PAD = 40;

/**
 * A to-scale sketch of the recorded location points, drawn locally from their coordinates.
 * There are no street-map tiles: the faint grid only gives a sense of shape and scale.
 */
export function RecordedRouteMap({ points }: { points: Point[] }) {
  const first = points[0];
  if (!first) return <p>No recorded locations remain for this trip.</p>;
  const latitude = points.reduce((total, point) => total + point.latitude, 0) / points.length;
  const scale = Math.max(0.01, Math.cos((latitude * Math.PI) / 180));
  let last = first.longitude;
  const coordinates = [];
  for (const point of points) {
    let longitude = point.longitude;
    while (longitude - last > 180) longitude -= 360;
    while (longitude - last < -180) longitude += 360;
    last = longitude;
    coordinates.push({ x: longitude * scale, y: -point.latitude });
  }
  const bounds = coordinates.reduce(
    (box, point) => ({
      minX: Math.min(box.minX, point.x),
      maxX: Math.max(box.maxX, point.x),
      minY: Math.min(box.minY, point.y),
      maxY: Math.max(box.maxY, point.y),
    }),
    { minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity },
  );
  const { minX, maxX, minY, maxY } = bounds;
  const factor = Math.min(
    (WIDTH - 2 * PAD) / Math.max(maxX - minX, 0.0001),
    (HEIGHT - 2 * PAD) / Math.max(maxY - minY, 0.0001),
  );
  const xy = coordinates.map((point) => ({
    x: WIDTH / 2 + (point.x - (minX + maxX) / 2) * factor,
    y: HEIGHT / 2 + (point.y - (minY + maxY) / 2) * factor,
  }));
  const grid = [1, 2, 3]
    .map((n) => `M0 ${(HEIGHT / 4) * n}H${WIDTH} M${(WIDTH / 4) * n} 0V${HEIGHT}`)
    .join(" ");
  return (
    <figure className="border-edge my-5 rounded-xl border p-3">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label="Route sketch of recorded trip locations, from start to end"
        className="bg-raised w-full rounded-lg"
      >
        <path d={grid} stroke="currentColor" opacity="0.1" />
        <polyline
          points={xy.map((point) => `${point.x},${point.y}`).join(" ")}
          fill="none"
          stroke="currentColor"
          strokeWidth="4"
          strokeLinejoin="round"
          className="text-cyan"
        />
        <circle cx={xy[0]!.x} cy={xy[0]!.y} r="9" className="fill-green" />
        <circle cx={xy.at(-1)!.x} cy={xy.at(-1)!.y} r="8" className="fill-amber" />
        <text x={WIDTH - 40} y="32" fill="currentColor" fontSize="18">
          N ↑
        </text>
      </svg>
      <figcaption className="mt-3 grid gap-2 text-sm">
        <span className="font-medium">Route sketch</span>
        <ul aria-label="Route sketch legend" className="text-muted flex flex-wrap gap-x-5 gap-y-1">
          <li className="flex items-center gap-2">
            <span aria-hidden className="bg-green inline-block size-3 rounded-full" />
            Start
          </li>
          <li className="flex items-center gap-2">
            <span aria-hidden className="bg-amber inline-block size-3 rounded-full" />
            End
          </li>
          <li className="flex items-center gap-2">
            <span aria-hidden className="bg-cyan inline-block h-1 w-5 rounded" />
            Recorded path ({points.length} locations)
          </li>
        </ul>
        <span className="text-muted">
          Drawn from the recorded locations only — not a street map. The grid shows scale, not
          streets. These records do not confirm that the trip was valid.
        </span>
      </figcaption>
      <p className="text-faint mt-1 text-xs">
        Start {first.latitude.toFixed(5)}, {first.longitude.toFixed(5)} · End{" "}
        {points.at(-1)!.latitude.toFixed(5)}, {points.at(-1)!.longitude.toFixed(5)}
      </p>
    </figure>
  );
}
