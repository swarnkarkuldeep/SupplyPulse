import { useEffect, useState } from "react";

const LINKS: { id: string; label: string }[] = [
  { id: "business", label: "Business" },
  { id: "delivery", label: "Delivery" },
  { id: "demand", label: "Demand" },
  { id: "inventory", label: "Inventory" },
  { id: "review", label: "Review pack" },
  { id: "trust", label: "Trust" },
];

/** A floating pill that stays small while you read, shows where you are, and opens on hover, focus or tap. */
export function Nav() {
  const [active, setActive] = useState<string | null>(null);
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 120);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const seen = new Map<string, boolean>();
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) seen.set(e.target.id, e.isIntersecting);
        const current = LINKS.find((l) => seen.get(l.id));
        setActive(current ? current.id : null);
      },
      { rootMargin: "-40% 0px -55% 0px" },
    );
    LINKS.forEach((l) => {
      const el = document.getElementById(l.id);
      if (el) io.observe(el);
    });
    return () => io.disconnect();
  }, []);

  const compact = scrolled && !open;
  const current = LINKS.find((l) => l.id === active);

  return (
    <header className="island-wrap">
      <nav
        className={`island ${compact ? "compact" : ""}`}
        aria-label="Sections"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false);
        }}
      >
        <a className="mark" href="#top" aria-label="SupplyPulse, back to top">
          <svg viewBox="0 0 32 32" aria-hidden="true">
            <path d="M3 22h6l3-12 5 16 3-10 2 6h5" />
          </svg>
          <span>SupplyPulse</span>
        </a>
        <button type="button" className="now" aria-expanded={!compact} onClick={() => setOpen((o) => !o)} tabIndex={compact ? 0 : -1}>
          {current ? current.label : "Menu"}
        </button>
        <div className="links">
          {LINKS.map((l) => (
            <a key={l.id} href={`#${l.id}`} aria-current={active === l.id ? "location" : undefined} onClick={() => setOpen(false)}>
              {l.label}
            </a>
          ))}
        </div>
      </nav>
    </header>
  );
}
