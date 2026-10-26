import "server-only";
import { cache } from "react";
import { createApiClient } from "@/lib/api/client";
import { getSessionToken } from "@/lib/auth/session";
import { readComplaintApi } from "./read";
import type { ComplaintParty } from "./labels";

/** Request-local read shared by the page title and the conversation. */
export const readOwnConversation = cache(async (party: ComplaintParty, complaintId: string) => {
  const api = createApiClient(await getSessionToken());
  return readComplaintApi(() =>
    party === "driver"
      ? api.GET("/api/v1/driver/complaints/{complaint_id}", {
          params: { path: { complaint_id: complaintId } },
        })
      : api.GET("/api/v1/advertiser/complaints/{complaint_id}", {
          params: { path: { complaint_id: complaintId } },
        }),
  );
});
