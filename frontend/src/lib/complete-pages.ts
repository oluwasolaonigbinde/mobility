import type { UnavailableReason } from "@/lib/advertiser/page-data";

export class IncompletePagesError extends Error {
  constructor(readonly reason: UnavailableReason = "protocol") {
    super("Incomplete list");
  }
}

/** Reads every page of a list, refusing a changing total, repeated rows or a short read. */
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
      throw new IncompletePagesError();
    }
    total = data.total;
    for (const row of data.items) {
      if (ids.has(row.id)) throw new IncompletePagesError();
      ids.add(row.id);
      rows.push(row);
    }
    if (rows.length > total) throw new IncompletePagesError();
  } while (rows.length < total);
  return rows;
}
