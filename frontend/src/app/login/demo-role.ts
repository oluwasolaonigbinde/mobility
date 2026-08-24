import { z } from "zod";

export const demoLoginRoleSchema = z.enum(["advertiser", "driver", "admin"]);
export type DemoLoginRole = z.infer<typeof demoLoginRoleSchema>;

export function demoLoginRoleFromPath(from: string | string[] | undefined): DemoLoginRole {
  if (typeof from !== "string") return "advertiser";

  for (const role of demoLoginRoleSchema.options) {
    if (from === `/${role}` || from.startsWith(`/${role}/`)) return role;
  }

  return "advertiser";
}
