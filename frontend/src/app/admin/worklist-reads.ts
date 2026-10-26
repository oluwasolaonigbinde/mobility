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
