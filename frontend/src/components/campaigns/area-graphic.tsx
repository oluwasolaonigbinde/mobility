import { geometryBounds, validateZoneGeometry, type ZoneGeometry } from "@/lib/zones/geometry";
import { useId } from "react";

type Area = { id: string; name: string; geometry: unknown; zone_type?: string };

/** Actual campaign boundaries on a quiet drawn grid; no streets or tile sources. */
export function AreaGraphic({
  areas,
  positions = [],
}: {
  areas: Area[];
  positions?: { longitude: number; latitude: number }[];
}) {
  const hatch = useId();
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
        <defs>
          <pattern id={hatch} width="8" height="8" patternUnits="userSpaceOnUse">
            <rect width="8" height="8" fill="#fff1f2" />
            <path d="M-2 2L2-2M0 8L8 0M6 10L10 6" stroke="#b02030" strokeWidth="1.5" />
          </pattern>
        </defs>
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
              fill={area.zone_type === "exclusion" ? `url(#${hatch})` : "#c8edbf"}
              fillOpacity="0.85"
              fillRule="evenodd"
              stroke={area.zone_type === "exclusion" ? "#b02030" : "#256f1a"}
              strokeWidth="2"
            />
          );
        })}
        {positions.map((point, index) => (
          <circle
            key={index}
            cx={x(point.longitude)}
            cy={y(point.latitude)}
            r="5"
            fill="#256f1a"
            stroke="#fff"
            strokeWidth="2"
          />
        ))}
        <path d="m365 37 5-15 5 15-5-4Z" fill="#0a1c09" />
      </svg>
    </div>
  );
}
