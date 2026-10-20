import { geometryBounds, validateZoneGeometry, type ZoneGeometry } from "@/lib/zones/geometry";

type Area = { id: string; name: string; geometry: Record<string, unknown> };

/** Actual campaign boundaries on a quiet drawn grid; no streets or tile sources. */
export function AreaGraphic({ areas }: { areas: Area[] }) {
  const valid = areas.filter((area) => validateZoneGeometry(area.geometry).ok);
  if (!valid.length)
    return (
      <div className="bg-raised text-ink flex h-full min-h-32 items-center justify-center p-5 text-center text-base">
        {areas.length ? "The area picture is unavailable." : "Choose an area for your campaign."}
      </div>
    );
  const boxes = valid.map((area) => geometryBounds(area.geometry as unknown as ZoneGeometry));
  const west = Math.min(...boxes.map((b) => b[0]));
  const south = Math.min(...boxes.map((b) => b[1]));
  const east = Math.max(...boxes.map((b) => b[2]));
  const north = Math.max(...boxes.map((b) => b[3]));
  const scale = Math.min(
    300 / Math.max(east - west, 0.0001),
    150 / Math.max(north - south, 0.0001),
  );
  const x = (value: number) => 200 + (value - (east + west) / 2) * scale;
  const y = (value: number) => 110 - (value - (north + south) / 2) * scale;
  return (
    <div className="relative h-full">
      <svg
        viewBox="0 0 400 220"
        role="img"
        aria-label={`Campaign areas: ${valid.map((a) => a.name).join(", ")}`}
        className="area-graphic"
        preserveAspectRatio="xMidYMid meet"
      >
        {[40, 80, 120, 160, 200, 240, 280, 320, 360].map((v) => (
          <path key={`v${v}`} d={`M${v} 0V220`} stroke="#e2ebdf" strokeWidth="1" />
        ))}
        {[30, 70, 110, 150, 190].map((v) => (
          <path key={`h${v}`} d={`M0 ${v}H400`} stroke="#e2ebdf" strokeWidth="1" />
        ))}
        {valid.map((area) => {
          const geometry = area.geometry as unknown as ZoneGeometry;
          const polygons =
            geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
          return (
            <path
              key={area.id}
              d={polygons
                .map((polygon) =>
                  polygon
                    .map(
                      (ring) =>
                        ring
                          .map(
                            ([lon, lat], i) =>
                              `${i ? "L" : "M"}${x(lon).toFixed(2)},${y(lat).toFixed(2)}`,
                          )
                          .join(" ") + "Z",
                    )
                    .join(" "),
                )
                .join(" ")}
              fill="#c8edbf"
              fillOpacity="0.85"
              fillRule="evenodd"
              stroke="#256f1a"
              strokeWidth="2"
            />
          );
        })}
        <path d="m365 37 5-15 5 15-5-4Z" fill="#0a1c09" />
      </svg>
      {/* HTML, not SVG text, so the label stays readable at any picture size. */}
      <span className="text-ink absolute bottom-3 left-3 inline-flex items-center gap-2 rounded-full bg-white px-3 py-1 text-[15px] font-semibold">
        <span aria-hidden="true" className="bg-green size-2 rounded-full" />
        Campaign area
      </span>
    </div>
  );
}
