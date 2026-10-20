// "2026-10-01" is a calendar date (a billing month), not a moment in time. Parse it as LOCAL
// midnight; `new Date("2026-10-01")` would be UTC and can show the previous day in some zones.
const local = (iso: string) => new Date(`${iso.slice(0, 10)}T00:00:00`);

const monthShort = new Intl.DateTimeFormat("en-IN", { month: "short" });
const monthLong = new Intl.DateTimeFormat("en-IN", { month: "long", year: "numeric" });
const day = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });
const time = new Intl.DateTimeFormat("en-IN", { hour: "numeric", minute: "2-digit" });
const weekday = new Intl.DateTimeFormat("en-IN", {
  weekday: "long",
  day: "numeric",
  month: "long",
});

export const monthShortLabel = (iso: string) => monthShort.format(local(iso));
export const monthLabel = (iso: string) => monthLong.format(local(iso));
export const calendarDay = (iso: string) => day.format(local(iso));

/** Moment-in-time helpers (ISO timestamps from the API). */
export const timeLabel = (iso: string) => time.format(new Date(iso));
export const dayHeading = (iso: string) => weekday.format(new Date(iso));
/** A stable key for grouping timestamps by the user's local day. */
export const dayKey = (iso: string) => new Date(iso).toLocaleDateString("en-CA");
