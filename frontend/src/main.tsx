import React from "react";
import ReactDOM from "react-dom/client";
import "./tokens.css";
import App from "./App";
import { registerOperatorPwa } from "./lib/pwaRegistration";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

registerOperatorPwa();
