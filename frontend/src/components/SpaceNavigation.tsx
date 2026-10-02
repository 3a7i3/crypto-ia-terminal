import React from "react";
import { Link, useLocation } from "react-router-dom";

/** Product navigation only. Machine and Research retain independent authorities. */
export const SpaceNavigation: React.FC = () => {
  const lab = useLocation().pathname.startsWith("/research");
  return (
    <nav
      className="space-navigation"
      aria-label="Machine et Laboratoire"
      data-testid="space-navigation"
    >
      <Link
        to="/direction"
        className={`space-link${!lab ? " space-link-active" : ""}`}
        aria-current={!lab ? "page" : undefined}
        data-testid="space-machine"
      >
        <span className="space-icon" aria-hidden="true">
          ◉
        </span>
        <span>
          <strong>Machine</strong>
          <small>État, portefeuille et marché</small>
        </span>
      </Link>
      <Link
        to="/research"
        className={`space-link space-link-lab${lab ? " space-link-active" : ""}`}
        aria-current={lab ? "page" : undefined}
        data-testid="tab-research"
      >
        <span className="space-icon" aria-hidden="true">
          ◇
        </span>
        <span>
          <strong>Laboratoire quantitatif</strong>
          <small>Recherche et évaluations</small>
        </span>
      </Link>
    </nav>
  );
};
