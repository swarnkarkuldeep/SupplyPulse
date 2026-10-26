import { Business } from "./components/Business";
import { Delivery } from "./components/Delivery";
import { Demand } from "./components/Demand";
import { Hero } from "./components/Hero";
import { Inventory } from "./components/Inventory";
import { Nav } from "./components/Nav";
import { ReviewPack } from "./components/ReviewPack";
import { Trust } from "./components/Trust";

export default function App() {
  return (
    <>
      <a className="skip" href="#top">
        Skip to content
      </a>
      <Nav />
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
