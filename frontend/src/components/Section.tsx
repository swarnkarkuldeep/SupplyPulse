import type { ReactNode } from "react";

interface Props {
  id: string;
  title: string;
  intro: ReactNode;
  children: ReactNode;
}

export function Section({ id, title, intro, children }: Props) {
  return (
    <section id={id} className="sec" aria-labelledby={`h-${id}`}>
      <div className="sec-head">
        <h2 id={`h-${id}`}>{title}</h2>
        <p>{intro}</p>
      </div>
      <div className="sec-body">{children}</div>
    </section>
  );
}

export function Figs({ items, stack }: { items: [string, string, string][]; stack?: boolean }) {
  return (
    <dl className={`figs ${stack ? "stack" : ""}`}>
      {items.map(([t, v, s]) => (
        <div key={t}>
          <dt>{t}</dt>
          <dd>
            {v}
            <small>{s}</small>
          </dd>
        </div>
      ))}
    </dl>
  );
}
