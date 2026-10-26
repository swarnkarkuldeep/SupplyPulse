import { useState } from "react";
import { data } from "../data";
import { int, monthLabel, ms, pct, usd, usdShort, yearTicks } from "../lib/format";
import { LineChart } from "./LineChart";
import { Figs, Section } from "./Section";

const R = data.results;

const METRICS = [
  { key: "revenue", label: "Revenue", fmt: usdShort, tip: usd },
  { key: "orders", label: "Orders", fmt: int, tip: int },
  { key: "margin_pct", label: "Margin", fmt: (v: number) => v.toFixed(0) + "%", tip: (v: number) => v.toFixed(1) + "%" },
  { key: "on_time_pct", label: "On time", fmt: (v: number) => v.toFixed(0) + "%", tip: (v: number) => v.toFixed(1) + "%" },
] as const;

export function Business() {
  const [key, setKey] = useState<(typeof METRICS)[number]["key"]>("revenue");
  const metric = METRICS.find((m) => m.key === key)!;
  return (
    <Section
      id="business"
      title="What the business looks like"
      intro={`Monthly figures for valid orders. ${pct(R.excluded_share)} of order lines were cancelled or suspected fraud, so they are flagged and left out of every analysis.`}
    >
      <div className="seg" role="group" aria-label="Metric">
        {METRICS.map((m) => (
          <button type="button" key={m.key} aria-pressed={m.key === key} onClick={() => setKey(m.key)}>
            {m.label}
          </button>
        ))}
      </div>
      <LineChart
        label={`${metric.label} by month`}
        series={[{ name: metric.label, color: "#101a2c", dots: true, width: 2.5, pts: data.monthly.map((r) => ({ x: ms(r.month), y: r[metric.key] })) }]}
        vlines={[{ x: ms(R.cutoff), label: `Volume drops ${pct(R.tail_drop_pct, 0)}` }]}
        yMin={0}
        yFmt={metric.fmt}
        xFmt={monthLabel}
        xTicks={yearTicks}
        tip={(_, p) => `${metric.label} ${metric.tip(p.y!)}`}
        legend={false}
      />
      <Figs
        items={[
          ["Revenue", usd(R.revenue), "valid orders, Jan 2015 to Jan 2018"],
          ["Profit", usd(R.profit), `${pct(R.margin)} margin`],
          ["On-time delivery", pct(R.on_time), `${int(R.orders)} orders`],
          ["Loss-making items", pct(R.loss_items_share), `they erase ${pct(R.loss_vs_gross_profit, 0)} of gross profit; 10 products hold ${pct(R.loss_top10_products, 0)} of the loss`],
        ]}
      />
    </Section>
  );
}
