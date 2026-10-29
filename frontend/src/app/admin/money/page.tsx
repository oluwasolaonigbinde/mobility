export const metadata = { title: "Money" };
import { requireRole } from "@/lib/auth/current-user";
import { PageHeader } from "@/components/ui/page-header";
import { ViewTabs } from "@/components/ui/tabs";
import { HubDrawer } from "../hub-drawer";
import Automatic from "../payouts/automatic/content";
import PaymentRuns, { ReadyToPay } from "../payouts/batches/content";
import RunContent from "../payouts/batches/[batchId]/content";
import PaymentContent from "../payouts/batches/[batchId]/lines/[lineId]/content";
import Corrections from "../payouts/corrections/content";
import Invoices from "./invoices";
import { moneyHref, moneyQuery, MONEY_TABS, type MoneySearch } from "./navigation";

/** One job per tab; run and payment details open in a drawer over the payout tabs. */
export default async function MoneyPage({ searchParams }: { searchParams: Promise<MoneySearch> }) {
  await requireRole("admin");
  const query = moneyQuery(await searchParams);
  const tab = MONEY_TABS.some(([value]) => value === query.tab) ? query.tab : "runs";
  const view = { ...query, tab };
  let drawer;
  const body =
    tab === "ready"
      ? await ReadyToPay({ searchParams: Promise.resolve(view) })
      : tab === "automatic"
        ? await Automatic({ searchParams: Promise.resolve(view) })
        : tab === "invoices"
          ? await Invoices({ query: view })
          : tab === "corrections"
            ? await Corrections({ query: view })
            : await PaymentRuns({ searchParams: Promise.resolve(view) });
  if (query.batch && tab !== "invoices" && tab !== "corrections") {
    const detail = query.line
      ? await PaymentContent({
          params: Promise.resolve({ batchId: query.batch, lineId: query.line }),
          searchParams: Promise.resolve(view),
        })
      : await RunContent({
          params: Promise.resolve({ batchId: query.batch }),
          searchParams: Promise.resolve(view),
        });
    drawer = (
      <HubDrawer
        title={query.line ? "Payment history" : "Payment run"}
        closeHref={moneyHref(view, {
          batch: undefined,
          line: undefined,
          line_page: undefined,
          history_page: undefined,
          draft_credits: undefined,
        })}
      >
        {detail}
      </HubDrawer>
    );
  }
  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader title="Money" />
      <ViewTabs
        label="Money tabs"
        items={MONEY_TABS.map(([value, label]) => ({
          href: moneyHref({}, { tab: value }),
          label,
          active: tab === value,
        }))}
      />
      {body}
      {drawer}
    </div>
  );
}
