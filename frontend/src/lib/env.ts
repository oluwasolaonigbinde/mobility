import "server-only";
import { z } from "zod";

const optionalString = <T extends z.ZodTypeAny>(schema: T) =>
  z.preprocess((value) => (value === "" ? undefined : value), schema.optional());

/**
 * Server-side environment configuration, validated at first use.
 * The FastAPI backend is never exposed to the browser; all calls go
 * through the Next.js server (BFF), so these stay server-only.
 */
const envSchema = z.object({
  API_BASE_URL: z.string().url().default("http://localhost:8000"),
  SESSION_COOKIE_NAME: z.string().min(1).default("mobility_session"),
  LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER: z
    .enum(["true", "false"])
    .default("false")
    .transform((value) => value === "true"),
  DEMO_LOGIN_ENABLED: z
    .enum(["true", "false"])
    .default("false")
    .transform((value) => value === "true"),
  DEMO_LOGIN_ADVERTISER_EMAIL: optionalString(z.string().trim().email()),
  DEMO_LOGIN_ADVERTISER_PASSWORD: optionalString(z.string().min(1)),
  DEMO_LOGIN_DRIVER_EMAIL: optionalString(z.string().trim().email()),
  DEMO_LOGIN_DRIVER_PASSWORD: optionalString(z.string().min(1)),
  DEMO_LOGIN_ADMIN_EMAIL: optionalString(z.string().trim().email()),
  DEMO_LOGIN_ADMIN_PASSWORD: optionalString(z.string().min(1)),
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
});

let cached: z.infer<typeof envSchema> | undefined;

export function env(): z.infer<typeof envSchema> {
  if (!cached) {
    const parsed = envSchema.safeParse({
      API_BASE_URL: process.env.API_BASE_URL,
      SESSION_COOKIE_NAME: process.env.SESSION_COOKIE_NAME,
      LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER: process.env.LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER,
      DEMO_LOGIN_ENABLED: process.env.DEMO_LOGIN_ENABLED,
      DEMO_LOGIN_ADVERTISER_EMAIL: process.env.DEMO_LOGIN_ADVERTISER_EMAIL,
      DEMO_LOGIN_ADVERTISER_PASSWORD: process.env.DEMO_LOGIN_ADVERTISER_PASSWORD,
      DEMO_LOGIN_DRIVER_EMAIL: process.env.DEMO_LOGIN_DRIVER_EMAIL,
      DEMO_LOGIN_DRIVER_PASSWORD: process.env.DEMO_LOGIN_DRIVER_PASSWORD,
      DEMO_LOGIN_ADMIN_EMAIL: process.env.DEMO_LOGIN_ADMIN_EMAIL,
      DEMO_LOGIN_ADMIN_PASSWORD: process.env.DEMO_LOGIN_ADMIN_PASSWORD,
      NODE_ENV: process.env.NODE_ENV,
    });
    if (!parsed.success) {
      throw new Error(`Invalid server environment: ${parsed.error.message}`);
    }
    cached = parsed.data;
  }
  return cached;
}
