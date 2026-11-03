export type MoneySearch = Record<string, string | string[] | undefined>;
/** Money tabs in display order; the first is the default. */
export const MONEY_TABS = [
  ["runs", "Payment runs"],
  ["ready", "Ready to pay"],
  ["automatic", "Automatic"],
  ["invoices", "Invoices"],
  ["corrections", "Corrections"],
] as const;
export function moneyQuery(query: MoneySearch): MoneyQuery {
  return Object.fromEntries(
    Object.entries(query).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string",
    ),
  );
}
export type MoneyQuery = Record<string, string | undefined>;
export function moneyHref(query: MoneyQuery, patch: MoneyQuery = {}) {
  const merged = { tab: "runs", ...query, ...patch };
  const params = new URLSearchParams(
    Object.entries(merged).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string",
    ),
  );
  return `/admin/money?${params}`;
}
export function moneyPage(value?: string) {
  return /^\d+$/.test(value ?? "") ? Math.min(Number(value), 100000) : 0;
}
export function MoneyQueryFields({ query, omit = [] }: { query: MoneyQuery; omit?: string[] }) {
  return (
    <>
      {Object.entries({ tab: "runs", ...query })
        .filter(([key, value]) => value !== undefined && !omit.includes(key))
        .map(([key, value]) => (
          <input type="hidden" key={key} name={key} value={value} />
        ))}
    </>
  );
}
