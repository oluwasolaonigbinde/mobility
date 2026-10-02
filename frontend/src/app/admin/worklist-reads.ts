export async function completePages<T extends { id: string }>(
  read: (offset: number) => Promise<{ data?: { items: T[]; total: number } }>,
): Promise<T[]> {
  const rows: T[] = [];
  const ids = new Set<string>();
  let total: number | undefined;
  do {
    const { data } = await read(rows.length);
    if (
      !data ||
      !Number.isSafeInteger(data.total) ||
      data.total < 0 ||
      (total !== undefined && data.total !== total) ||
      (!data.items.length && rows.length < data.total)
    ) {
      throw new Error("Incomplete work list");
    }
    total = data.total;
    for (const row of data.items) {
      if (ids.has(row.id)) throw new Error("Duplicate work list row");
      ids.add(row.id);
      rows.push(row);
    }
    if (rows.length > total) throw new Error("Invalid work list count");
  } while (rows.length < total);
  return rows;
}

export function worklistHref(
  base: string,
  current: Record<string, string | undefined>,
  changes: Record<string, string | undefined>,
) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries({ ...current, ...changes }))
    if (value !== undefined && value !== "") query.set(key, value);
  return query.size ? `${base}?${query}` : base;
}
