import { useMemo, useState } from "react";
import { data } from "../data";
import { cap, int, modelName, pct } from "../lib/format";
import { Bars } from "./Bars";
import { Figs, Section } from "./Section";

const risk = data.risk;
const chosen = risk.champion;
const chosenThr = Math.round(risk.metrics[chosen].threshold * 1000);

export function Delivery() {
  const [thr, setThr] = useState(chosenThr);
  const hj = data.delivery.hour_jump[0];

  const counts = useMemo(() => {
    const { s, y } = risk.scores;
    const lateTotal = [...y].reduce((a, c) => a + (c === "1" ? 1 : 0), 0);
    let tp = 0;
    let fp = 0;
    for (let i = 0; i < s.length; i++) if (s[i] >= thr) (y[i] === "1" ? tp++ : fp++);
    const n = s.length;
    return { n, lateTotal, tp, fp, fn: lateTotal - tp, tn: n - lateTotal - fp };
  }, [thr]);

  const { n, lateTotal, tp, fp, fn, tn } = counts;
  const aucs = (["shipping_mode_only", "logistic", "lightgbm"] as const).map((k) => [k, risk.metrics[k].roc_auc] as const);
  const gain = risk.metrics[chosen].roc_auc - risk.metrics.shipping_mode_only.roc_auc;
  const topShare = risk.drivers[0].share;

  return (
    <Section
      id="delivery"
      title="Who delivers late, and can a model see it coming?"
      intro="Shipping mode explains most of lateness. A model adds a little on top, and a threshold decides how many alerts you are willing to chase."
    >
      <h3>Late rate by shipping mode</h3>
      <Bars
        rows={data.delivery.by_mode.map((m) => ({
          label: m.shipping_mode,
          sub: `${m.scheduled_days === 0 ? "same day" : `${m.scheduled_days} ${m.scheduled_days === 1 ? "day" : "days"}`} promised, ${int(m.orders)} orders`,
          value: m.late,
          shown: pct(m.late, 0),
          cls: "late",
        }))}
      />
      {hj && (
        <p className="note">
          {hj.shipping_mode} orders placed before noon are late <b>{pct(hj.late_before, 0)}</b> of the time ({int(hj.orders_before)} orders). From noon on,{" "}
          <b>{pct(hj.late_after, 0)}</b> are ({int(hj.orders_after)} orders). Real carriers do not behave like a switch, which is one sign this dataset
          is synthetic.
        </p>
      )}

      <h3>Late-order alerts</h3>
      <p className="note">
        Drag the threshold. An order is flagged when its risk score is at or above it. These are the held-out test orders: the most recent 20% by
        date, never seen in training.
      </p>
      <div className="control">
        <label htmlFor="thr">
          Flag orders with a score of at least <output>{(thr / 1000).toFixed(2)}</output>
        </label>
        <input id="thr" type="range" min={50} max={950} step={1} value={thr} onChange={(e) => setThr(+e.target.value)} />
        <button type="button" className="btn" onClick={() => setThr(chosenThr)}>
          Use the threshold picked on validation data ({risk.metrics[chosen].threshold.toFixed(2)})
        </button>
      </div>
      <div className="alert-grid">
        <div className="matrix" aria-live="polite">
          <span />
          <span className="h">Flagged late</span>
          <span className="h">Not flagged</span>
          <span className="h rh">Actually late</span>
          <div className="cell good"><b>{int(tp)}</b><span>caught</span></div>
          <div className="cell bad"><b>{int(fn)}</b><span>missed</span></div>
          <span className="h rh">Actually on time</span>
          <div className="cell bad"><b>{int(fp)}</b><span>false alarms</span></div>
          <div className="cell good"><b>{int(tn)}</b><span>correctly left alone</span></div>
        </div>
        <Figs
          stack
          items={[
            ["Precision", tp + fp ? pct(tp / (tp + fp)) : "n/a", "of flagged orders really were late"],
            ["Recall", pct(tp / lateTotal), "of late orders were flagged"],
            ["Flagged", pct((tp + fp) / n, 0), `of ${int(n)} test orders`],
            ["Base rate", pct(lateTotal / n), "of test orders were late"],
          ]}
        />
      </div>

      <h3>How much of this is just shipping mode?</h3>
      <Bars rows={aucs.map(([k, v]) => ({ label: modelName(k), sub: "ROC-AUC on test orders", value: v, shown: v.toFixed(3), min: 0.5, max: 1, cls: k === chosen ? "hi" : undefined }))} />
      <p className="note">
        Bars start at 0.5, which is a coin flip. Knowing only the shipping mode gets <b>{risk.metrics.shipping_mode_only.roc_auc.toFixed(3)}</b>; the
        full model adds <b>{gain.toFixed(3)}</b>. The honest summary is a useful model whose lift over a one-column baseline is modest.
      </p>

      <h3>What the model leans on</h3>
      <Bars rows={risk.drivers.map((d) => ({ label: cap(d.feature.replace(/_/g, " ")), value: d.share, shown: pct(d.share, 0), max: topShare * 1.05 }))} />
    </Section>
  );
}
