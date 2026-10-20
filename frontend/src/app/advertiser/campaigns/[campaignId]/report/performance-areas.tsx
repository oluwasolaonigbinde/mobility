import type { components } from "@/lib/api/schema";
import { formatCount } from "@/lib/format";
import { Panel } from "@/components/ui/panel";

export function PerformanceAreas({
  areas,
}: {
  areas: components["schemas"]["CampaignPerformanceRead"]["areas"];
}) {
  return (
    <Panel className="mt-6 overflow-hidden">
      <h2 className="border-edge border-b p-5 font-semibold">Results by area</h2>
      {!areas.length ? (
        <p className="text-muted p-5 text-sm">
          Area results aren’t available for this period. You can still see your campaign totals.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-muted">
                <th scope="col" className="p-4 font-normal">
                  Area
                </th>
                <th scope="col" className="p-4 text-right font-normal">
                  Trips
                </th>
                <th scope="col" className="p-4 text-right font-normal">
                  Estimated views
                </th>
              </tr>
            </thead>
            <tbody>
              {areas.map((area) => (
                <tr key={area.area_id} className="border-edge border-t">
                  <th scope="row" className="p-4 font-medium">
                    {area.name}
                  </th>
                  <td className="p-4 text-right">{formatCount(area.trip_count)}</td>
                  <td className="p-4 text-right">
                    {formatCount(area.modelled_potential_contacts)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
