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

/** The last month of a cycle that starts at `iso` ("2026-10-01" + 3 months -> December 2026). */
const cycleEnd = (iso: string, cycleMonths: number) => {
  const start = local(iso);
  return new Date(start.getFullYear(), start.getMonth() + cycleMonths - 1, 1);
};

/** "October 2026" for a monthly cycle; "Oct–Dec 2026" for a quarterly one. */
export const cycleLabel = (iso: string, cycleMonths: number) =>
  cycleMonths <= 1
    ? monthLabel(iso)
    : `${monthShort.format(local(iso))}–${monthShort.format(cycleEnd(iso, cycleMonths))} ${local(iso).getFullYear()}`;

/** A compact column heading: "Oct" monthly, "Oct–Dec" quarterly. */
export const cycleShortLabel = (iso: string, cycleMonths: number) =>
  cycleMonths <= 1
    ? monthShort.format(local(iso))
    : `${monthShort.format(local(iso))}–${monthShort.format(cycleEnd(iso, cycleMonths))}`;

/** The word for one cycle: "month" or "quarter". */
export const cycleWord = (cycleMonths: number) => (cycleMonths === 3 ? "quarter" : "month");

/** The first day of the next cycle after today, as "YYYY-MM-DD": a sensible billing start. */
export function nextCycleStart(cycleMonths: number, today = new Date()): string {
  const index = today.getFullYear() * 12 + today.getMonth();
  const next = (Math.floor(index / cycleMonths) + 1) * cycleMonths;
  const year = Math.floor(next / 12);
  const month = (next % 12) + 1;
  return `${year}-${String(month).padStart(2, "0")}-01`;
}

/** The first days of the next `count` cycles after today: the dates billing may start on. */
export function upcomingCycleStarts(cycleMonths: number, count = 6, today = new Date()): string[] {
  const out: string[] = [];
  let from = today;
  for (let i = 0; i < count; i++) {
    const next = nextCycleStart(cycleMonths, from);
    out.push(next);
    from = new Date(`${next}T00:00:00`);
  }
  return out;
}

/** Moment-in-time helpers (ISO timestamps from the API). */
export const timeLabel = (iso: string) => time.format(new Date(iso));
export const dayHeading = (iso: string) => weekday.format(new Date(iso));
/** A stable key for grouping timestamps by the user's local day. */
export const dayKey = (iso: string) => new Date(iso).toLocaleDateString("en-CA");
