import { fileResponse } from "../_proxy";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  return fileResponse(async (api) =>
    api.POST("/api/v1/advertiser/files/uploads", {
      body: await request.json(),
    }),
  );
}
