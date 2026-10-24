// Building and downloading CSV files in the browser. Nothing here leaves the device.

// A cell that starts with one of these is run as a FORMULA by Excel and Sheets ("=HYPERLINK(...)").
// A resident's name is typed by someone else, so every cell is defused with a leading apostrophe.
const FORMULA_START = /^[=+\-@\t\r]/;

export function csvCell(value: string): string {
  const safe = FORMULA_START.test(value) ? `'${value}` : value;
  return /[",\n\r]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

export function toCsv(rows: string[][]): string {
  return rows.map((row) => row.map(csvCell).join(",")).join("\r\n") + "\r\n";
}

/** Save `rows` as a file. The byte-order mark makes Excel read accents and rupee signs correctly. */
export function downloadCsv(filename: string, rows: string[][]) {
  const blob = new Blob(["﻿", toCsv(rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
