// Small helpers shared by the superadmin pages.
export const SUB_KIND = { Active: "good", Expiring: "warn", Expired: "bad", "No expiry": "gray" };
export const usageKind = (p) => (p >= 90 ? "bad" : p >= 70 ? "warn" : "good");
/** School row -> initial values for the edit form (null date becomes an empty input). */
export const schoolInitial = (s) => ({ ...s, subscription_end: s.subscription_end ?? "" });
