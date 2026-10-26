import { data } from "../data";
import { dayLabel, int, pct } from "../lib/format";
import { Figs, Section } from "./Section";

const R = data.results;
const F = data.forecast;

const LIMITS = [
  `The dataset looks synthetic. Same Day orders switch from 0% to 100% late at noon, and margin barely moves with discount (R-squared ${R.discount_r2.toFixed(3)}), so the findings say more about the method than about retail.`,
  "The simulation's costs and supplier lead times are assumptions, not measurements. Change them in config.yaml and rerun.",
  "The discount and margin regression shows association, not cause.",
  `Weekly volume falls by about ${pct(R.tail_drop_pct, 0)} after ${dayLabel(R.cutoff)} and the data does not say why, so forecasts stop there.`,
  `The backtest is ${R.folds} windows of ${R.horizon_weeks ?? F.horizon_weeks} weeks. SARIMA beating a moving average by ${((R.wape_ma - R.wape) * 100).toFixed(1)} points is inside that noise.`,
  "The number check proves every number in the review matches a fact. It does not prove the wording is right, so the text is a draft for a person to read.",
  "The Power BI report is not built; the measures, theme and page specs are in dashboard/. The SQL Server load through pyodbc has not been run on this machine; the T-SQL was validated on SQL Server 2022 in Docker and the pipeline runs on SQLite.",
];

export function Trust() {
  return (
    <Section id="trust" title="What to trust, and what not to" intro="A project is only as useful as its limits are clear. These are the ones I know about.">
      <Figs
        items={[
          ["Automated data checks", int(R.dq_checks), `${R.dq_failing_errors} failures at error level, ${R.dq_failing_warnings} warnings`],
          ["Tests", int(R.tests), "including a leakage guard and a simulation check against a known answer"],
          ["Rows kept", int(R.rows_clean), `of ${int(R.rows_raw)}; cancelled and fraud orders are flagged, not deleted`],
          ["DAX measures", int(R.dax_measures), "written and tested against the schema"],
        ]}
      />
      <h3>Limits, stated plainly</h3>
      <ul className="limits">
        {LIMITS.map((l) => (
          <li key={l}>{l}</li>
        ))}
      </ul>
      <h3>Run it yourself</h3>
      <pre className="cmd" tabIndex={0}>
        <code>{`python -m sca all        # ingest, check, load, forecast, risk model, simulation, KPIs, review pack
python -m sca site       # rebuild this app's data from those outputs
cd frontend && npm run dev`}</code>
      </pre>
    </Section>
  );
}
