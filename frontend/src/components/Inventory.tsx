import { useState } from "react";
import { data } from "../data";
import { int, pct, usd } from "../lib/format";
import { niceTicks } from "../lib/format";
import { LineChart } from "./LineChart";
import { Section } from "./Section";

const A = data.assumptions;
const cats = Object.keys(data.inventory).sort();
const targets = [...new Set(data.inventory[cats[0]].grid.map((g) => g.analytic_service_target).filter((v): v is number => v != null))].sort();

export function Inventory() {
  const [cat, setCat] = useState(cats[0]);
  const [target, setTarget] = useState(targets.includes(0.95) ? 0.95 : targets[0]);

  const grid = data.inventory[cat].grid;
  const textbook = grid.filter((g) => g.basis === "textbook").sort((a, b) => a.holding_cost - b.holding_cost);
  const aware = grid.filter((g) => g.basis === "lead_time_aware").sort((a, b) => a.holding_cost - b.holding_cost);
  const tb = textbook.find((g) => g.analytic_service_target === target)!;
  const fix = aware.find((g) => g.cycle_service_level >= target);
  const miss = tb.cycle_service_level < target - 0.005;
  const extra = fix ? fix.holding_cost / tb.holding_cost - 1 : null;
  const pts = (rows: typeof grid) => rows.map((g) => ({ x: g.holding_cost, y: g.cycle_service_level, e: g.safety_stock }));

  return (
    <Section
      id="inventory"
      title="How much safety stock is enough?"
      intro={`The textbook formula assumes supplier lead time is fixed. Simulating ${int(A.paths)} years of weekly orders with lead times of ${A.lead_time_weeks.join(", ")} weeks shows how far the formula falls short, and what closing the gap costs.`}
    >
      <div className="control row">
        <label htmlFor="icat">Category</label>
        <select id="icat" value={cat} onChange={(e) => setCat(e.target.value)}>
          {cats.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
        <label htmlFor="svc">Service you ask for</label>
        <select id="svc" value={target} onChange={(e) => setTarget(+e.target.value)}>
          {targets.map((t) => (
            <option key={t} value={t}>
              {pct(t, 0)}
            </option>
          ))}
        </select>
      </div>
      <div className="inv-read" aria-live="polite">
        <div className={miss ? "miss" : "hit"}>
          <h4>Textbook formula for {pct(target, 0)}</h4>
          <b>{pct(tb.cycle_service_level, 1)}</b>
          <p>
            simulated service with {int(tb.safety_stock)} units of safety stock, holding cost {usd(tb.holding_cost)} a year.
          </p>
        </div>
        <div className="hit">
          <h4>Sized for lead-time variability</h4>
          {fix && extra != null ? (
            <>
              <b>{int(fix.safety_stock)} units</b>
              <p>
                reaches {pct(fix.cycle_service_level, 1)} simulated service at {usd(fix.holding_cost)} a year ({extra >= 0 ? "+" : ""}
                {pct(extra, 0)} versus the textbook stock).
              </p>
            </>
          ) : (
            <>
              <b>not reached</b>
              <p>no tested stock level reaches {pct(target, 0)}.</p>
            </>
          )}
        </div>
      </div>
      <LineChart
        label="Simulated service level against yearly holding cost"
        series={[
          { name: "Textbook formula", color: "#c8381f", dots: true, pts: pts(textbook) },
          { name: "Sized for lead-time variability", color: "#1e7b5c", dots: true, pts: pts(aware) },
        ]}
        hlines={[{ y: target, label: `You asked for ${pct(target, 0)}` }]}
        yMin={Math.min(0.5, ...aware.map((g) => g.cycle_service_level))}
        left={56}
        yFmt={(v) => pct(v, 0)}
        xFmt={usd}
        xTicks={(a, b) => niceTicks(a, b, 5)}
        tip={(s, p) => `${s.name}: ${int(p.e ?? 0)} units, ${pct(p.y!, 1)} service`}
      />
      <p className="note">
        Service here means the share of replenishment cycles with no stockout. Assumptions, not measurements: lead times of {A.lead_time_weeks.join(", ")}{" "}
        weeks with probabilities {A.lead_time_probs.map((p) => pct(p, 0)).join(", ")}, and a holding cost of {pct(A.holding_cost_pct_per_week, 1)} of
        unit cost per week.
      </p>
    </Section>
  );
}
