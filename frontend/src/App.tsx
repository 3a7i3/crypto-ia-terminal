import React from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./tokens.css";
import "./operator.css";
import "./clarity.css";
import "./mobile-operator.css";
import "./workspace.css";
import { AppFrame } from "./shells/AppFrame";
import { DirectionShell } from "./shells/DirectionShell";
import { PaperLiveShell } from "./shells/PaperLiveShell";
import { ResearchShell } from "./shells/ResearchShell";
import {
  DecisionsRoute,
  FinanceRoute,
  LifecycleRoute,
  MarketRoute,
  PortfolioRoute,
  SystemRoute,
} from "./router/PaperLiveRoutes";
import { ModuleHome } from "./views/ModuleHome";
import { MachineWorkboardView } from "./views/MachineWorkboardView";
import { EventsView } from "./views/EventsView";
import { NotFoundView } from "./views/NotFoundView";
import { ResearchStrategyBoardView } from "./views/ResearchStrategyBoardView";
import { ResearchLabView } from "./views/ResearchLabView";

const App: React.FC = () => (
  <BrowserRouter>
    <Routes>
      <Route element={<AppFrame />}>
        <Route path="/" element={<Navigate to="/direction" replace />} />
        <Route path="/paper-live" element={<PaperLiveShell />}>
          <Route index element={<Navigate to="/direction" replace />} />
          <Route
            path="overview"
            element={<Navigate to="/direction" replace />}
          />
          <Route path="market" element={<MarketRoute />} />
          <Route path="portfolio" element={<PortfolioRoute />} />
          <Route
            path="burn-in"
            element={<Navigate to="/paper-live/portfolio" replace />}
          />
          <Route path="decisions" element={<DecisionsRoute />} />
          <Route path="lifecycle" element={<LifecycleRoute />} />
          <Route path="finance" element={<FinanceRoute />} />
          <Route path="events" element={<EventsView />} />
          <Route path="system" element={<SystemRoute />} />
          <Route
            path="scores"
            element={<Navigate to="/paper-live/system" replace />}
          />
        </Route>
        <Route path="/direction" element={<DirectionShell />}>
          <Route index element={<ModuleHome />} />
          <Route path="travaux" element={<MachineWorkboardView />} />
        </Route>
        <Route path="/research" element={<ResearchShell />}>
          <Route index element={<ResearchLabView />} />
          <Route path="strategies" element={<ResearchStrategyBoardView />} />
        </Route>
        <Route path="*" element={<NotFoundView />} />
      </Route>
    </Routes>
  </BrowserRouter>
);

export default App;
