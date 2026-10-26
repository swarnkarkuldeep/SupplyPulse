import { useState } from "react";
import { data } from "../data";
import { dayLabel, int, modelName, monthLabel, ms, pct, quarterTicks } from "../lib/format";
import { Bars } from "./Bars";
import { LineChart, type Series } from "./LineChart";
import { Section } from "./Section";

const R = data.results;
const F = data.forecast;
const cats = Object.keys(F.categories).sort();

export function Demand() {
  const [cat, setCat] = useState(cats[0]);
  const [showBack, setShowBack] = useState(true);
  const c = F.categories[cat];

  const dedupe = (rows: [string, number, number][]) => [...new Map(rows.map((r) => [r[0], r])).values()].sort((a, b) => a[0].localeCompare(b[0]));
  const series: Series[] = [{ name: "Actual units per week", color: "#101a2c", width: 2, pts: c.history.map((r) => ({ x: ms(r[0]), y: r[1] })) }];
  if (showBack)
    series.push({ name: `Backtest (${modelName(F.champion)})`, color: "#2b5c9e", dash: "5 4", pts: dedupe(c.backtest).map((r) => ({ x: ms(r[0]), y: r[2] })) });
  series.push({ name: `Forecast (${modelName(F.champion)})`, color: "#2b5c9e", width: 2.75, pts: c.forecast.map((r) => ({ x: ms(r[0]), y: r[1] })) });

  const maxW = Math.max(...F.models.map((m) => m.wape));
  const gapPts = ((R.wape_ma - R.wape) * 100).toFixed(1);

  return (
    <Section
      id="demand"
      title="How much will each category sell?"
      intro={`Each category gets a weekly forecast, tested the way it would be used: train on the past, predict the next ${F.horizon_weeks} weeks, repeat ${F.folds} times. Forecasts end at ${dayLabel(F.cutoff)}, where weekly volume in this dataset falls by about ${pct(R.tail_drop_pct, 0)} for reasons the data does not explain.`}
    >
      <div className="control row">
        <label htmlFor="cat">Category</label>
        <select id="cat" value={cat} onChange={(e) => setCat(e.target.value)}>
          {cats.map((x) => (
            <option key={x}>{x}</option>
          ))}
        </select>
        <label className="check">
          <input type="checkbox" checked={showBack} onChange={(e) => setShowBack(e.target.checked)} /> Show the backtest
        </label>
      </div>
      <LineChart
        label={`Weekly units for ${cat}: history, backtest and forecast`}
        series={series}
        bands={[{ name: `${pct(data.assumptions.interval_level, 0)} prediction interval`, color: "#2b5c9e", pts: c.forecast.map((r) => ({ x: ms(r[0]), lo: r[2], hi: r[3] })) }]}
        vlines={[{ x: ms(F.cutoff), label: "Forecast starts" }]}
        yFmt={int}
        xFmt={dayLabel}
        tickFmt={monthLabel}
        xTicks={quarterTicks}
        tip={(s, p) => `${(s.name ?? "").split(" (")[0]}: ${int(p.y!)} units`}
      />
      <p className="note">
        {cat}: {modelName(F.champion)} is wrong by <b>{c.wape != null ? pct(c.wape) : "n/a"}</b> on average in the backtest (WAPE, error as a share of
        units sold). The forecast is a central estimate with a band, not a promise.
      </p>
      <h3>Five models, same five tests</h3>
      <Bars
        rows={[...F.models]
          .sort((a, b) => a.wape - b.wape)
          .map((m) => ({ label: modelName(m.model), sub: m.model === F.champion ? "champion" : undefined, value: m.wape, shown: pct(m.wape), max: maxW * 1.08, cls: m.model === F.champion ? "hi" : undefined }))}
      />
      <p className="note">
        Lower is better. The champion beats the seasonal-naive baseline by <b>{pct(R.wape_improvement, 0)}</b>, but a moving average is only <b>{gapPts} points</b>{" "}
        behind, which is inside the noise of a {F.folds}-fold backtest. A simple model is a fair choice here.
      </p>
    </Section>
  );
}
