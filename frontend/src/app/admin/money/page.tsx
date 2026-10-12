export const metadata = { title: "Money" };
import { requireRole } from "@/lib/auth/current-user";
import { PageHeader } from "@/components/ui/page-header";
import { ViewTabs } from "@/components/ui/tabs";
import { HubDrawer } from "../hub-drawer";
import Automatic from "../payouts/automatic/content";
import PaymentRuns from "../payouts/batches/content";
import RunContent from "../payouts/batches/[batchId]/content";
import PaymentContent from "../payouts/batches/[batchId]/lines/[lineId]/content";
import Corrections from "../payouts/corrections/content";
import Invoices from "./invoices";
import { moneyHref, moneyQuery, type MoneySearch } from "./navigation";
export default async function MoneyPage({ searchParams }: { searchParams: Promise<MoneySearch> }) {
  await requireRole("admin");
  const query = moneyQuery(await searchParams);
  const tab = ["payouts", "invoices", "corrections"].includes(query.tab ?? "")
    ? query.tab
    : "payouts";
  let body, drawer;
  if (tab === "payouts") {
    const [automatic, runs] = await Promise.all([
      Automatic({ searchParams: Promise.resolve(query), embedded: true }),
      PaymentRuns({ searchParams: Promise.resolve(query) }),
    ]);
    body = (
      <>
        {automatic}
        {runs}
      </>
    );
    if (query.batch) {
      const detail = query.line
        ? await PaymentContent({
            params: Promise.resolve({ batchId: query.batch, lineId: query.line }),
            searchParams: Promise.resolve(query),
          })
        : await RunContent({
            params: Promise.resolve({ batchId: query.batch }),
            searchParams: Promise.resolve(query),
          });
      drawer = (
        <HubDrawer
          title={query.line ? "Payment history" : "Payment run"}
          closeHref={moneyHref(query, {
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
  } else body = tab === "invoices" ? await Invoices({ query }) : await Corrections({ query });
  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader title="Money" />
      <ViewTabs
        label="Money tabs"
        items={[
          ["payouts", "Payouts"],
          ["invoices", "Invoices & payments"],
          ["corrections", "Corrections"],
        ].map(([value, label]) => ({
          href: moneyHref(query, {
            tab: value,
            batch: undefined,
            line: undefined,
            correction: undefined,
          }),
          label,
          active: tab === value,
        }))}
      />
      {body}
      {drawer}
    </div>
  );
}
