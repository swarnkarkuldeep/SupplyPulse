import { Business } from "./components/Business";
import { Delivery } from "./components/Delivery";
import { Demand } from "./components/Demand";
import { Hero } from "./components/Hero";
import { Inventory } from "./components/Inventory";
import { ReviewPack } from "./components/ReviewPack";
import { Trust } from "./components/Trust";

const NAV: [string, string][] = [
  ["#business", "Business"],
  ["#delivery", "Delivery"],
  ["#demand", "Demand"],
  ["#inventory", "Inventory"],
  ["#review", "Review pack"],
  ["#trust", "Trust"],
];

export default function App() {
  return (
    <>
      <a className="skip" href="#top">
        Skip to content
      </a>
      <header className="bar">
        <a className="mark" href="#top" aria-label="SupplyPulse, back to top">
          <svg viewBox="0 0 32 32" aria-hidden="true">
            <path d="M3 22h6l3-12 5 16 3-10 2 6h5" />
          </svg>
          SupplyPulse
        </a>
        <nav aria-label="Sections">
          {NAV.map(([href, label]) => (
            <a key={href} href={href}>
              {label}
            </a>
          ))}
        </nav>
      </header>
      <main id="top">
        <Hero />
        <Business />
        <Delivery />
        <Demand />
        <Inventory />
        <ReviewPack />
        <Trust />
      </main>
      <footer className="foot">
        <p>
          Data: DataCo Smart Supply Chain (public Kaggle dataset). Every number on this page is read from files the pipeline wrote; the build step is{" "}
          <code>src/sca/site.py</code>.
        </p>
      </footer>
    </>
  );
}
