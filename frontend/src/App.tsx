import React from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./tokens.css";
import "./operator.css";
import "./clarity.css";
import "./mobile-operator.css";
import { DirectionShell } from "./shells/DirectionShell";
import { PaperLiveShell } from "./shells/PaperLiveShell";
import { ResearchShell } from "./shells/ResearchShell";
import {
  DecisionsRoute,
  FinanceRoute,
  LifecycleRoute,
  MarketRoute,
  OverviewRoute,
  PortfolioRoute,
  ScoresRoute,
  SystemRoute,
} from "./router/PaperLiveRoutes";
import { DirectionOverview } from "./views/DirectionOverview";
import { BurnInStatusView } from "./views/BurnInStatusView";
import { EventsView } from "./views/EventsView";
import { NotFoundView } from "./views/NotFoundView";
import { ResearchStrategyBoardView } from "./views/ResearchStrategyBoardView";
import { ResearchLabView } from "./views/ResearchLabView";

const App: React.FC = () => (
  <BrowserRouter>
    <Routes>
      <Route path="/" element={<Navigate to="/direction" replace />} />
      <Route path="/paper-live" element={<PaperLiveShell />}>
        <Route index element={<OverviewRoute />} />
        <Route path="overview" element={<OverviewRoute />} />
        <Route path="market" element={<MarketRoute />} />
        <Route path="portfolio" element={<PortfolioRoute />} />
        <Route path="burn-in" element={<BurnInStatusView />} />
        <Route path="decisions" element={<DecisionsRoute />} />
        <Route path="lifecycle" element={<LifecycleRoute />} />
        <Route path="finance" element={<FinanceRoute />} />
        <Route path="events" element={<EventsView />} />
        <Route path="system" element={<SystemRoute />} />
        <Route path="scores" element={<ScoresRoute />} />
      </Route>
      <Route path="/direction" element={<DirectionShell />}>
        <Route index element={<DirectionOverview />} />
      </Route>
      <Route path="/research" element={<ResearchShell />}>
        <Route index element={<ResearchLabView />} />
        <Route path="strategies" element={<ResearchStrategyBoardView />} />
      </Route>
      <Route path="*" element={<NotFoundView />} />
    </Routes>
  </BrowserRouter>
);

export default App;
