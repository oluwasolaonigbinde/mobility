import type { components } from "@/lib/api/schema";

type Point = components["schemas"]["AdminTripRoutePointRead"];

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
  const factor = Math.min(520 / Math.max(maxX - minX, 0.0001), 240 / Math.max(maxY - minY, 0.0001));
  const xy = coordinates.map((point) => ({
    x: 300 + (point.x - (minX + maxX) / 2) * factor,
    y: 150 + (point.y - (minY + maxY) / 2) * factor,
  }));
  return (
    <figure className="border-edge my-5 rounded-xl border p-3">
      <svg
        viewBox="0 0 600 300"
        role="img"
        aria-label="Map of recorded trip locations, from start to end"
        className="bg-raised w-full rounded-lg"
      >
        <path
          d="M0 75H600 M0 150H600 M0 225H600 M150 0V300 M300 0V300 M450 0V300"
          stroke="currentColor"
          opacity="0.1"
        />
        <polyline
          points={xy.map((point) => `${point.x},${point.y}`).join(" ")}
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
          className="text-cyan"
        />
        <circle cx={xy[0]!.x} cy={xy[0]!.y} r="6" className="fill-green" />
        <circle cx={xy.at(-1)!.x} cy={xy.at(-1)!.y} r="5" className="fill-amber" />
        <text x="570" y="25" fill="currentColor" fontSize="14">
          N ↑
        </text>
      </svg>
      <figcaption className="text-muted mt-2 text-sm">
        Recorded route · green start, amber end · {points.length} locations. These records do not
        confirm that the trip was valid.
      </figcaption>
      <p className="text-muted mt-1 text-xs">
        Start {first.latitude.toFixed(5)}, {first.longitude.toFixed(5)} · End{" "}
        {points.at(-1)!.latitude.toFixed(5)}, {points.at(-1)!.longitude.toFixed(5)}
      </p>
    </figure>
  );
}
