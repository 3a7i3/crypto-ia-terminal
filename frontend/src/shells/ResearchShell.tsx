import React from "react";
import { NavLink, Outlet } from "react-router-dom";
import { ModuleHeading } from "../components/ModuleHeading";
export const ResearchShell: React.FC = () => (
  <div data-testid="research-shell">
    <ModuleHeading
      title="Laboratoire"
      description="Évaluations publiées et stratégies étudiées."
      badge={
        <span
          className="source-pill"
          data-testid="research-header-domain-badge"
        >
          RECHERCHE NON AUTORITAIRE
        </span>
      }
    />
    <nav className="module-subnav" aria-label="Vues Laboratoire">
      <NavLink to="/research" end>
        Évaluations et preuves
      </NavLink>
      <NavLink to="/research/strategies" data-testid="lab-strategies-link">
        Stratégies
      </NavLink>
    </nav>
    <Outlet />
  </div>
);
