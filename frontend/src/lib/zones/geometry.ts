/**
 * Client-side mirror of the backend's GeoJSON zone rules
 * (app/services/campaign_zones.py): Polygon/MultiPolygon only, linear
 * rings closed with ≥ 4 positions, coordinates are finite [lon, lat]
 * pairs within bounds. The backend stays authoritative (it additionally
 * enforces the max-area cap in PostGIS).
 */

export type Position = [number, number];

export interface PolygonGeometry {
  type: "Polygon";
  coordinates: Position[][];
}

export interface MultiPolygonGeometry {
  type: "MultiPolygon";
  coordinates: Position[][][];
}

export type ZoneGeometry = PolygonGeometry | MultiPolygonGeometry;

export type GeometryValidation = { ok: true } | { ok: false; reason: string };

function validatePosition(p: unknown): string | null {
  if (!Array.isArray(p) || p.length < 2) return "Positions must be [longitude, latitude] pairs";
  const [lon, lat] = p as number[];
  if (typeof lon !== "number" || typeof lat !== "number") {
    return "Coordinates must be numbers";
  }
  if (!Number.isFinite(lon) || !Number.isFinite(lat)) return "Coordinates must be finite";
  if (lon < -180 || lon > 180) return "Longitude must be between -180 and 180";
  if (lat < -90 || lat > 90) return "Latitude must be between -90 and 90";
  return null;
}

function validateRing(ring: unknown): string | null {
  if (!Array.isArray(ring) || ring.length < 4) {
    return "Polygon rings must contain at least four positions";
  }
  for (const pos of ring) {
    const err = validatePosition(pos);
    if (err) return err;
  }
  const first = ring[0] as number[];
  const last = ring[ring.length - 1] as number[];
  if (first[0] !== last[0] || first[1] !== last[1]) {
    return "Polygon rings must be closed (first position equals last)";
  }
  return null;
}

function validatePolygonCoords(coords: unknown): string | null {
  if (!Array.isArray(coords) || coords.length < 1) {
    return "Polygon must include at least one linear ring";
  }
  for (const ring of coords) {
    const err = validateRing(ring);
    if (err) return err;
  }
  return null;
}

export function validateZoneGeometry(geometry: unknown): GeometryValidation {
  if (typeof geometry !== "object" || geometry === null) {
    return { ok: false, reason: "Geometry must be a GeoJSON object" };
  }
  const g = geometry as { type?: unknown; coordinates?: unknown };
  if (g.type === "Polygon") {
    const err = validatePolygonCoords(g.coordinates);
    return err ? { ok: false, reason: err } : { ok: true };
  }
  if (g.type === "MultiPolygon") {
    if (!Array.isArray(g.coordinates) || g.coordinates.length < 1) {
      return { ok: false, reason: "MultiPolygon must include at least one polygon" };
    }
    for (const poly of g.coordinates) {
      const err = validatePolygonCoords(poly);
      if (err) return { ok: false, reason: err };
    }
    return { ok: true };
  }
  return { ok: false, reason: "Geometry must be a Polygon or MultiPolygon" };
}

/** Bounding box [west, south, east, north] for zoom-to-zone. */
export function geometryBounds(geometry: ZoneGeometry): [number, number, number, number] {
  let west = Infinity,
    south = Infinity,
    east = -Infinity,
    north = -Infinity;
  const rings: Position[][] =
    geometry.type === "Polygon" ? geometry.coordinates : geometry.coordinates.flat();
  for (const ring of rings) {
    for (const [lon, lat] of ring) {
      if (lon < west) west = lon;
      if (lon > east) east = lon;
      if (lat < south) south = lat;
      if (lat > north) north = lat;
    }
  }
  return [west, south, east, north];
}
