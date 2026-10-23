/** Campaign statuses the backend can cancel; others are refused or already finished. */
export function isCancellableCampaign(status: string) {
  return ["approved", "active", "paused"].includes(status);
}
