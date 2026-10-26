import type { ReactNode } from "react";
import { data } from "../data";
import { int, pct } from "../lib/format";

const R = data.results;

const ROWS: { q: string; a: ReactNode; to: string; see: string }[] = [
  {
    q: "Are orders arriving on time?",
    a: (
      <>
        <b>{pct(R.on_time)}</b> of {int(R.orders)} orders were on time. First Class orders were late {pct(R.late_first_class, 0)} of the time.
      </>
    ),
    to: "#delivery",
    see: "Delivery",
  },
  {
    q: "Which orders will be late?",
    a: (
      <>
        A model reaches <b>ROC-AUC {R.roc_auc.toFixed(2)}</b> on orders it never saw. Shipping mode alone reaches {R.roc_auc_mode_only.toFixed(2)}.
      </>
    ),
    to: "#delivery",
    see: "Delivery",
  },
  {
    q: "How much will each category sell?",
    a: (
      <>
        SARIMA forecasts weekly units with <b>{pct(R.wape)} error</b> over {R.n_categories} categories, {pct(R.wape_improvement, 0)} better than
        repeating last year. A plain moving average is {((R.wape_ma - R.wape) * 100).toFixed(1)} points behind.
      </>
    ),
    to: "#demand",
    see: "Demand",
  },
  {
    q: "How much safety stock is enough?",
    a: (
      <>
        The textbook formula aims for 95% service and delivers <b>{pct(R.textbook_service_95, 0)}</b> once supplier lead times vary.
      </>
    ),
    to: "#inventory",
    see: "Inventory",
  },
  {
    q: "Can the written review be trusted?",
    a: <>Every number in it must match a fact from the database. A made-up number is rejected. You can try it.</>,
    to: "#review",
    see: "Review pack",
  },
];

export function Hero() {
  return (
    <section className="hero" aria-labelledby="h-hero">
      <h1 id="h-hero">
        <span>{pct(R.on_time)}</span> of orders arrive on time.
      </h1>
      <p className="lede">
        SupplyPulse reads {int(R.rows_clean)} order lines from a sports-goods retailer (the public DataCo dataset), keeps {int(R.orders)} valid orders,
        and answers five operating questions with a database, a late-delivery model, a demand forecast and an inventory simulation. Every number on
        this page was produced by code you can run.
      </p>
      <div className="manifest" role="table" aria-label="Questions this project answers">
        <div className="m-head" role="row">
          <span role="columnheader">Question</span>
          <span role="columnheader">What the data says</span>
          <span role="columnheader">See</span>
        </div>
        {ROWS.map((r, i) => (
          <a className="m-row" role="row" key={r.q} style={{ "--i": i } as React.CSSProperties} href={r.to}>
            <span className="m-q" role="cell">
              {r.q}
            </span>
            <span className="m-a" role="cell">
              {r.a}
            </span>
            <span className="m-go" role="cell">
              {r.see}
            </span>
          </a>
        ))}
      </div>
    </section>
  );
}
