export const int = (n: number) => Math.round(n).toLocaleString("en-US");
export const pct = (x: number, d = 1) => (x * 100).toFixed(d) + "%";
export const usd = (n: number) => "$" + int(n);
export const usdShort = (n: number) =>
  Math.abs(n) >= 1e6 ? "$" + (n / 1e6).toFixed(1) + "M" : Math.abs(n) >= 1e3 ? "$" + Math.round(n / 1e3) + "k" : "$" + Math.round(n);
export const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

const asDate = (v: string | number) => new Date(typeof v === "string" ? v + "T00:00:00Z" : v);
export const monthLabel = (v: string | number) =>
  asDate(v).toLocaleDateString("en-US", { month: "short", year: "numeric", timeZone: "UTC" });
export const dayLabel = (v: string | number) =>
  asDate(v).toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
export const monthName = (period: string) =>
  new Date(period + "-01T00:00:00Z").toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" });
export const ms = (iso: string) => Date.parse(iso + "T00:00:00Z");

const MODEL: Record<string, string> = {
  seasonal_naive: "Seasonal naive",
  moving_average: "Moving average",
  sarima: "SARIMA",
  prophet: "Prophet",
  lightgbm: "LightGBM",
  logistic: "Logistic regression",
  shipping_mode_only: "Shipping mode only",
};
export const modelName = (k: string) => MODEL[k] ?? cap(k.replace(/_/g, " "));

export function niceTicks(lo: number, hi: number, n = 4): number[] {
  const span = hi - lo || 1;
  const raw = span / n;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? mag * 10;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}

export const yearTicks = (a: number, b: number): number[] => {
  const out: number[] = [];
  for (let y = new Date(a).getUTCFullYear(); y <= new Date(b).getUTCFullYear() + 1; y++) {
    const t = Date.UTC(y, 0, 1);
    if (t >= a && t <= b) out.push(t);
  }
  return out;
};

export const quarterTicks = (a: number, b: number): number[] => {
  const out: number[] = [];
  for (let y = new Date(a).getUTCFullYear(); y <= new Date(b).getUTCFullYear(); y++) {
    for (let q = 0; q < 12; q += 3) {
      const t = Date.UTC(y, q, 1);
      if (t >= a && t <= b) out.push(t);
    }
  }
  return out;
};
