import { Fragment, useMemo, useState } from "react";
import { data, type Fact, type Pack } from "../data";
import { cap, monthName } from "../lib/format";
import { allowedYears, checkLine, parseBlocks, tamper as makeTamper, tokenize, type Tamper } from "../lib/grounding";
import { Section } from "./Section";

type Selected = { kind: "idle" } | { kind: "fact"; id: string; key: string } | { kind: "bad"; token: string; key: string } | { kind: "tamper"; fake: string };

const IDLE: Selected = { kind: "idle" };

function unit(f: Fact, v: number | string): string {
  if (typeof v !== "number") return String(v);
  if (f.unit === "USD") return "$" + v.toLocaleString("en-US", { maximumFractionDigits: 2 });
  if (f.unit === "%") return v + "%";
  if (f.unit === "pp") return v + " pp";
  return `${v.toLocaleString("en-US")} ${f.unit ?? ""}`.trim();
}

function FactPanel({ pack, sel }: { pack: Pack; sel: Selected }) {
  if (sel.kind === "idle")
    return (
      <>
        <h4>Source of a number</h4>
        <p className="muted">Click a number or a citation such as [F1] in the text above.</p>
      </>
    );
  if (sel.kind === "tamper")
    return (
      <>
        <h4>You changed a number</h4>
        <p>
          Now it reads <b>{sel.fake}</b>.
        </p>
        <p className="muted">No fact cited on that line says so. Click the red number to see what the check reports.</p>
      </>
    );
  if (sel.kind === "bad")
    return (
      <>
        <h4>No cited fact says this</h4>
        <p>
          <b>{sel.token}</b>
        </p>
        <p className="muted">The facts cited on this line do not contain that number, so the check rejects the line.</p>
      </>
    );
  const f = pack.facts.find((x) => x.id === sel.id);
  if (!f) return null;
  return (
    <>
      <h4>
        {f.id}: {f.metric}
      </h4>
      <p>
        <b>{unit(f, f.value)}</b> <span className="muted">for {f.period}</span>
      </p>
      {f.comparison_value != null && (
        <p className="muted">
          Compared with {unit(f, f.comparison_value)} ({f.comparison_period ?? ""})
          {f.delta != null && `; change ${f.delta > 0 ? "+" : ""}${f.delta}${f.delta_unit === "%" ? "%" : ` ${f.delta_unit ?? ""}`}`}
        </p>
      )}
      <p className="muted">
        From <code>sql/sqlserver/kpi_queries/{f.source_query}.sql</code>, query checksum <code>{pack.query_checksum}</code>
      </p>
    </>
  );
}

function attemptLine(a: Pack["validation"]["attempts"][number], i: number) {
  const who = cap(a.provider ?? "model");
  if (a.error) {
    const code = a.error.match(/(\d{3}) ([A-Z_]+)/);
    return (
      <li className="fail" key={i}>
        {who}: request failed ({code ? `${code[1]} ${code[2]}` : "error"}).
      </li>
    );
  }
  if (a.ok)
    return (
      <li className="pass" key={i}>
        {who}: draft passed, {a.numbers_checked} numbers checked.
      </li>
    );
  return (
    <li className="fail" key={i}>
      {who}: draft rejected, {a.offending_numbers.join(", ") || "uncited line"} not supported by a cited fact.
    </li>
  );
}

export function ReviewPack() {
  const [index, setIndex] = useState(0);
  const [tampered, setTampered] = useState<Tamper | null>(null);
  const [sel, setSel] = useState<Selected>(IDLE);
  const pack = data.packs[index];
  const v = pack.validation;

  const years = useMemo(() => allowedYears(pack.facts), [pack]);
  const blocks = useMemo(() => parseBlocks(pack.markdown), [pack]);

  const lines = blocks.map((b, bi) => {
    const text = tampered && tampered.block === bi ? tampered.text : b.text;
    const checks = b.kind === "h" ? [] : checkLine(text, pack.facts, years);
    return { b, bi, text, checks };
  });
  const total = lines.reduce((n, l) => n + l.checks.filter((c) => !c.isYear).length, 0);
  const bad = lines.reduce((n, l) => n + l.checks.filter((c) => !c.ok).length, 0);

  const choosePack = (i: number) => {
    setIndex(i);
    setTampered(null);
    setSel(IDLE);
  };

  const renderLine = (l: (typeof lines)[number]) => {
    const parts = tokenize(l.text, pack.facts, years);
    return parts.map((p, i) => {
      const key = `${l.bi}:${i}`;
      if (p.kind === "text") return <Fragment key={i}>{p.bold ? <strong>{p.text}</strong> : p.text}</Fragment>;
      if (p.kind === "cite")
        return (
          <button type="button" key={i} className="cite" aria-pressed={sel.kind === "fact" && sel.key === key} aria-label={`Fact ${p.id}`} onClick={() => setSel({ kind: "fact", id: p.id, key })}>
            {p.id}
          </button>
        );
      return (
        <button
          type="button"
          key={i}
          className={`num ${p.ok ? "" : "bad"}`}
          aria-pressed={(sel.kind === "fact" || sel.kind === "bad") && sel.key === key}
          onClick={() => setSel(p.ok && p.fact ? { kind: "fact", id: p.fact.id, key } : { kind: "bad", token: p.text, key })}
        >
          {p.text}
        </button>
      );
    });
  };

  const rejected = (l: (typeof lines)[number]) => l.checks.some((c) => !c.ok);
  const out: React.ReactNode[] = [];
  let list: { ordered: boolean; items: React.ReactNode[] } | null = null;
  const flush = () => {
    if (!list) return;
    const Tag = list.ordered ? "ol" : "ul";
    out.push(<Tag key={`list-${out.length}`}>{list.items}</Tag>);
    list = null;
  };
  for (const l of lines) {
    if (l.b.kind === "li") {
      if (list && list.ordered !== !!l.b.ordered) flush();
      list ??= { ordered: !!l.b.ordered, items: [] };
      list.items.push(
        <li key={l.bi}>
          <span className={`line ${rejected(l) ? "rejected" : ""}`}>{renderLine(l)}</span>
        </li>,
      );
      continue;
    }
    flush();
    if (l.b.kind === "h") out.push(<h4 key={l.bi}>{l.b.text}</h4>);
    else
      out.push(
        <p key={l.bi}>
          <span className={`line ${rejected(l) ? "rejected" : ""}`}>{renderLine(l)}</span>
        </p>,
      );
  }
  flush();

  return (
    <Section
      id="review"
      title="A monthly review that shows its work"
      intro="A language model drafts the monthly review from a fixed list of facts. A checker then reads every line: each number must match a fact cited on that line, or the draft is rejected. Click any number or citation to see its source."
    >
      <div className="control row">
        <label htmlFor="pack">Month</label>
        <select id="pack" value={index} onChange={(e) => choosePack(+e.target.value)}>
          {data.packs.map((p, i) => (
            <option key={p.period} value={i}>
              {monthName(p.period)}
            </option>
          ))}
        </select>
        <span className={`pill ${v.mode === "llm" ? "llm" : ""}`}>{v.mode === "llm" ? `Written by ${cap(v.provider ?? "a model")}` : "Template text"}, number-checked</span>
      </div>
      <article className="paper">{out}</article>
      <div className={`check-bar ${bad > 0 ? "fail" : ""}`} aria-live="polite">
        {bad === 0 ? (
          <>
            {total} of {total} numbers match a fact cited on the same line.
            <small>This page re-implements the rule from src/sca/grounding.py so you can try it here.</small>
          </>
        ) : (
          <>
            {total - bad} of {total} numbers match. {bad} {bad === 1 ? "does" : "do"} not, so this draft would be rejected.
            <small>The pipeline would send the model the error once, then fall back to the template text, which passes the same check.</small>
          </>
        )}
      </div>
      <div className="control row">
        {tampered ? (
          <button
            type="button"
            className="btn ghost"
            onClick={() => {
              setTampered(null);
              setSel(IDLE);
            }}
          >
            Put it back
          </button>
        ) : (
          <button
            type="button"
            className="btn"
            onClick={() => {
              const t = makeTamper(blocks, pack.facts, years);
              setTampered(t);
              if (t) setSel({ kind: "tamper", fake: t.fake });
            }}
          >
            Change one number
          </button>
        )}
      </div>
      <details className="attempts">
        <summary>
          How this text was produced ({v.attempts.length} model {v.attempts.length === 1 ? "attempt" : "attempts"})
        </summary>
        <ol>
          {v.attempts.map(attemptLine)}
          {v.mode === "template" && (
            <li className="pass">Fell back to the deterministic template, which passes the same check{v.reason ? ` (${v.reason})` : ""}.</li>
          )}
        </ol>
      </details>
      <aside className="fact" aria-live="polite">
        <FactPanel pack={pack} sel={sel} />
      </aside>
    </Section>
  );
}
