export function formatCurrency(amount: number | string | null | undefined, currency = "USD"): string {
  if (amount === null || amount === undefined || amount === "") return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(Number(amount));
}

export function formatNumber(value: number | string | null | undefined, digits = 0): string {
  if (value === null || value === undefined || value === "") return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(Number(value));
}

export function formatPct(value: number | string | null | undefined, digits = 1): string {
  if (value === null || value === undefined || value === "") return "—";
  return `${Number(value).toFixed(digits)}%`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-US", { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function relativeTime(value: string | null | undefined): string {
  if (!value) return "—";
  const diff = Date.now() - new Date(value).getTime();
  // Timestamps can sit slightly in the future (clock skew, scheduled dates),
  // so phrase both directions rather than emitting a negative "ago".
  const ahead = diff < 0;
  const say = (n: number, unit: string) => (ahead ? `in ${n} ${unit}` : `${n} ${unit} ago`);
  const minutes = Math.round(Math.abs(diff) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return say(minutes, "min");
  const hours = Math.round(minutes / 60);
  if (hours < 24) return say(hours, "h");
  const days = Math.round(hours / 24);
  if (days < 30) return say(days, "d");
  return formatDate(value);
}

export function titleCase(value: string | null | undefined): string {
  if (!value) return "";
  return value.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function todayIso(offsetDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}
