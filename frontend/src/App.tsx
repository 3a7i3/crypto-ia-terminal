import React from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import "./tokens.css";
import "./operator.css";
import "./clarity.css";
import "./mobile-operator.css";
import "./workspace.css";
import "./radar-polish.css";
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
  PaperOrderHistoryRoute,
  SystemRoute,
} from "./router/PaperLiveRoutes";

import { MachineWorkboardView } from "./views/MachineWorkboardView";
import { EventsView } from "./views/EventsView";
import { NotFoundView } from "./views/NotFoundView";
import { ResearchStrategyBoardView } from "./views/ResearchStrategyBoardView";
import { ResearchLabView } from "./views/ResearchLabView";
import { MARKET_RADAR_PATH } from "./lib/moduleNavigation";

// M1-C1 (EO-022, D-C5): Market stays the home during M1. Former entry points land
// on the canonical Radar route with replace, keeping their query so historical
// bookmarks (?intraday=1) keep their meaning. Since M1-C3 (EO-024) an obsolete
// ?radar=0 is dropped by the Radar view itself and opens Radar Spot.
const HomeRedirect: React.FC = () => {
  const { search } = useLocation();
  return <Navigate to={{ pathname: MARKET_RADAR_PATH, search }} replace />;
};

const App: React.FC = () => (
  <BrowserRouter>
    <Routes>
      <Route element={<AppFrame />}>
        <Route path="/" element={<HomeRedirect />} />
        <Route path="/paper-live" element={<PaperLiveShell />}>
          <Route index element={<HomeRedirect />} />
          <Route path="overview" element={<HomeRedirect />} />
          <Route path="market/*" element={<MarketRoute />} />
          <Route path="portfolio" element={<PortfolioRoute />} />
          <Route path="order-history" element={<PaperOrderHistoryRoute />} />
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
          <Route index element={<HomeRedirect />} />
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
