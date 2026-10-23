import { validateZoneGeometry, type ZoneGeometry } from "./geometry";

/** Read the Polygon/MultiPolygon WKT already frozen into an accepted driver job. */
export function frozenGeometry(value: unknown): ZoneGeometry | null {
  if (typeof value !== "string") return null;
  const match = value.trim().match(/^(POLYGON|MULTIPOLYGON)\s*(\(.*\))$/i);
  if (!match?.[1] || !match[2]) return null;
  const number = "[-+]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][-+]?\\d+)?";
  const pair = new RegExp(`(?<=[(,])\\s*(${number})\\s+(${number})\\s*(?=[,)])`, "g");
  try {
    const coordinates = JSON.parse(
      match[2]
        .replace(pair, (_pair, longitude: string, latitude: string) =>
          JSON.stringify([Number(longitude), Number(latitude)]),
        )
        .replaceAll("(", "[")
        .replaceAll(")", "]"),
    );
    const geometry = {
      type: match[1].toUpperCase() === "POLYGON" ? "Polygon" : "MultiPolygon",
      coordinates,
    };
    return validateZoneGeometry(geometry).ok ? (geometry as ZoneGeometry) : null;
  } catch {
    return null;
  }
}
