"use client";

import { useState } from "react";
import { MoneyQueryFields, type MoneyQuery } from "../../money/navigation";

/**
 * Search for available earnings. Searching is off while both boxes are empty and no search is
 * applied, so an empty submit never reloads the page for nothing.
 */
export function EarningsSearch({ query }: { query: MoneyQuery }) {
  const [q, setQ] = useState(query.q ?? "");
  const [currency, setCurrency] = useState(query.currency ?? "");
  const applied = Boolean(query.q || query.currency);
  const empty = !q.trim() && !currency.trim();
  return (
    <form className="flex flex-wrap gap-3">
      <MoneyQueryFields query={query} omit={["q", "currency", "credits"]} />
      <input
        aria-label="Search driver or campaign"
        name="q"
        value={q}
        onChange={(event) => setQ(event.currentTarget.value)}
        placeholder="Driver or campaign name"
        maxLength={100}
        className="border-edge bg-raised min-w-0 flex-1 rounded-lg border px-3 py-2"
      />
      <input
        aria-label="Filter currency"
        name="currency"
        value={currency}
        onChange={(event) => setCurrency(event.currentTarget.value)}
        placeholder="Currency"
        maxLength={3}
        className="border-edge bg-raised w-24 rounded-lg border px-3 py-2 uppercase"
      />
      <button
        disabled={empty && !applied}
        className="border-edge rounded-lg border px-4 py-2 disabled:opacity-50"
      >
        {empty && applied ? "Show all earnings" : "Search earnings"}
      </button>
    </form>
  );
}
