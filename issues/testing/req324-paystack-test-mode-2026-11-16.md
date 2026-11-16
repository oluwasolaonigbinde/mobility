# REQ-324 Paystack test-mode run, 16 November 2026

**Result:** checkout, public webhook delivery and replay pass. The one test payout is blocked by seed data and failed safely. The owner chose to stop there and prove the payout later.

## Setup
- **Code under test:** master `0afb936e`. The API and worker ran the bind-mounted checkout; the images were built 15 Nov at `ed719ef3`, with the same backend dependencies.
- **Key:** the Paystack account's **test** secret key (`sk_test_`). It came from the owner's local access file into a temporary scratch env file that was deleted at teardown. The key was never printed.
- **Stack:** an isolated Compose project `cv-req324`, with CPU and memory limits.
  - The API and website were bound to loopback only (`127.0.0.1:18000`, `127.0.0.1:13300`); no other host ports.
  - A throwaway Caddy edge served only `/api/v1/webhooks/paystack` (1 MiB cap, production header stripping) to a temporary Cloudflare quick tunnel.
- **Seed:** the local demo seed.
- **Payouts:** automatic payouts were paused before the worker started (`paused: true`, `provider_ready: true`, `runnable: false`).
- **Tunnel probe:** `GET /`, `/api/v1/health` and `/admin` returned 404. An unsigned `POST /api/v1/webhooks/paystack` returned 401.
- **Dashboard:** the owner set the Test Webhook URL to the tunnel. It was empty before. The tunnel no longer exists, so that setting now points nowhere until it is replaced or cleared.

## Checkout and webhook (pass)
- **REQ-325 refusal:** a seeded cancelled campaign's invoice was refused with `409 CAMPAIGN_CANCELLED_NO_PAYMENT`.
- **Checkout:** invoice TXM-2025-000010 (₦1,000,000 gross, ₦500,000 already funded) got a real Paystack test checkout for the ₦500,000 balance.
- **Payment:** Paystack's checkout page sits behind a Cloudflare bot check that blocks headless browsers. It was not bypassed; the owner paid in their own browser with Paystack's test card.
- **Webhook:** Paystack's `charge.success` arrived through the tunnel and returned 200.
  - One gateway event was recorded (₦500,000, `payment_confirmed`).
  - The checkout became `confirmed`.
  - The invoice shows `funded_amount` 1,000,000.00 and `payment_status` `paid`.

## Replay (pass)
- The transaction was read back from Paystack's `/transaction/verify` (`success`, NGN 50,000,000 kobo, reference matches).
- It was wrapped as a `charge.success` event, signed with the test key and posted through the tunnel twice. Both returned 200 with `duplicate: true`.
- There is still one gateway event, one allocation and one confirmed checkout.

## One test payout (blocked by seed data, failed safely)
- **Batch:** one seeded manual line of ₦563.85. It was approved and submitted, and the worker sent it.
- **Refusal:** Paystack refused the first step, creating the transfer recipient, with 400 "Cannot resolve account".
  - Paystack test mode still verifies the bank account. The seed uses a placeholder (GTBank `058`, `0000000000`), and Paystack's test bank list has no test bank.
  - No recipient or transfer was created on Paystack.
- **Cardvert's response:** it set the submission intent to `query_only`, meaning the outcome is unknown and it will only check, never resend. The line stayed reserved, and no money moved.

## Still needed for W2-01C
- **Transfers:** proof of one transfer to a real, verifiable account.
- **Recovery:** proof after a missed webhook. The verify path was already proven locally on 29 Sep 2026.
- **Live setup:** the hosted production domain, the live key and its webhook URL, and production approval.
