export function QueueSearch({
  q = "",
  label = "Search this work list",
  children,
}: {
  q?: string;
  label?: string;
  children?: React.ReactNode;
}) {
  return (
    <form className="mb-5 flex flex-wrap items-end gap-3" role="search">
      <label className="text-muted flex min-w-0 flex-1 flex-col gap-1 text-sm">
        {label}
        <input
          name="q"
          defaultValue={q}
          maxLength={120}
          className="border-edge bg-raised text-ink h-11 min-w-0 rounded-lg border px-3"
        />
      </label>
      {children}
      <button className="bg-amber text-bg h-11 rounded-lg px-4" type="submit">
        Search
      </button>
    </form>
  );
}

export function QueueUnavailable() {
  return (
    <p role="alert" className="border-coral/40 text-coral rounded-lg border p-4">
      This work list is unavailable. Reload to try again. No empty or complete result has been
      confirmed.
    </p>
  );
}
