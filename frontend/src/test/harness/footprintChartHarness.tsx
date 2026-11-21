// Banc visuel local : rend FootprintChart sur la fixture SYNTHETIC de 20 bougies M1 pour
// vérifier espacements et alignements. Servi par le serveur de développement Vite
// (test-harness/footprint-chart.html) ; jamais inclus dans le build de production.
import ReactDOM from "react-dom/client";
import "../../tokens.css";
import "../../footprint.css";
import { FootprintChart } from "../../components/FootprintChart";
import { buildFootprintModel } from "../../lib/footprintModel";
import { syntheticTwentyBars } from "../footprintSyntheticTwentyBars";

const params = new URLSearchParams(window.location.search);
const theme = params.get("theme") === "dark" ? "dark" : "light";
const model = buildFootprintModel(syntheticTwentyBars(), 60_000, 1, 24);
document.body.style.margin = "0";
ReactDOM.createRoot(document.getElementById("root")!).render(
  <section className="market-panel footprint-panel" data-testid="footprint-panel" data-footprint-theme={theme} aria-label="Footprint SYNTHETIC">
    <p className="footprint-badge footprint-badge-warn" data-testid="synthetic-banner">SYNTHETIC · fixture de test, aucune donnée réelle · 20 bougies M1</p>
    <FootprintChart model={model} step={1} />
  </section>,
);
