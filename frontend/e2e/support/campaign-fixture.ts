import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { resolve } from "node:path";

const COMPOSE_FILE = resolve(__dirname, "../../../docker-compose.yml");

function psql(sql: string, variables: Record<string, string>) {
  const databaseContainer = process.env.E2E_DATABASE_CONTAINER;
  const databaseName = process.env.E2E_DATABASE_NAME ?? "mobility";
  const variableArgs = Object.entries(variables).flatMap(([name, value]) => [
    "-v",
    `${name}=${value}`,
  ]);
  const args = databaseContainer
    ? ["exec", "-i", databaseContainer, "psql"]
    : ["compose", "-f", COMPOSE_FILE, "exec", "-T", "db", "psql"];
  execFileSync(
    "docker",
    [...args, "-v", "ON_ERROR_STOP=1", ...variableArgs, "-U", "mobility", "-d", databaseName],
    { input: sql, stdio: ["pipe", "pipe", "pipe"] },
  );
}

export function createIsolatedActiveCampaign(label: string) {
  const campaignId = randomUUID();
  const campaignName = `${label} ${randomUUID()}`;
  psql(
    `
INSERT INTO campaigns (
  id, organization_id, created_by_user_id, name, description, status,
  start_at, end_at, budget_amount, daily_budget_amount, currency, metadata
)
SELECT
  :'campaign_id'::uuid, organization_id, created_by_user_id, :'campaign_name',
  description, 'active', start_at, end_at, budget_amount, daily_budget_amount,
  currency, jsonb_build_object('synthetic_e2e_fixture', true)
FROM campaigns
WHERE name = 'Demo Lagos Mobility Campaign';

SELECT 1 / CASE WHEN count(*) = 1 THEN 1 ELSE 0 END
FROM campaigns WHERE id = :'campaign_id'::uuid;
`,
    { campaign_id: campaignId, campaign_name: campaignName },
  );
  return { campaignId, campaignName };
}

export function cleanupIsolatedCampaign(campaignId: string) {
  psql(
    `
SET session_replication_role = replica;
DELETE FROM campaign_cancellation_settlement_revisions WHERE campaign_id = :'campaign_id'::uuid;
DELETE FROM campaign_change_revisions WHERE campaign_id = :'campaign_id'::uuid;
DELETE FROM campaign_change_requests WHERE campaign_id = :'campaign_id'::uuid;
DELETE FROM campaign_cancellations WHERE campaign_id = :'campaign_id'::uuid;
DELETE FROM campaigns WHERE id = :'campaign_id'::uuid;
RESET session_replication_role;

SELECT 1 / CASE WHEN count(*) = 0 THEN 1 ELSE 0 END
FROM campaigns WHERE id = :'campaign_id'::uuid;
`,
    { campaign_id: campaignId },
  );
}
