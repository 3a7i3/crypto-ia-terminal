import React, { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { AppIcon } from "../components/AppIcon";
import { AppearanceSettings } from "../components/AppearanceSettings";
import { useDisplayLayout } from "../lib/useDisplayLayout";
import { MARKET_RADAR_PATH, MODULES } from "../lib/moduleNavigation";

export const AppFrame: React.FC = () => {
  useDisplayLayout();
  const { pathname } = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    setMenuOpen(false);
    document.getElementById("app-content")?.focus({ preventScroll: true });
  }, [pathname]);
  // The Accueil shortcut (D-C5) points into Market and never claims the active state.
  const active = MODULES.find(
    (m) =>
      (m.testId !== "tab-overview" && m.to === pathname) ||
      (m.testId === "tab-market" && pathname.startsWith("/paper-live/market/")) ||
      (m.to === "/research" && pathname.startsWith("/research/")) ||
      (m.to.endsWith("/portfolio") && (pathname.endsWith("/lifecycle") || pathname.endsWith("/order-history"))),
  );
  return (
    <div
      className="app-frame operator-shell"
      onKeyDown={(e) => {
        if (e.key === "Escape" && menuOpen) {
          setMenuOpen(false);
          toggle.current?.focus();
        }
      }}
    >
      <a className="app-skip" href="#app-content">
        Aller au contenu
      </a>
      <header className="app-topbar">
        <button
          className="icon-button mobile-menu-toggle"
          ref={toggle}
          aria-label={menuOpen ? "Fermer les modules" : "Ouvrir les modules"}
          aria-expanded={menuOpen}
          aria-controls="module-sidebar"
          onClick={() => setMenuOpen(!menuOpen)}
        >
          <AppIcon name={menuOpen ? "close" : "menu"} />
        </button>
        <Link className="app-brand" to={MARKET_RADAR_PATH}>
          <span className="app-brand-symbol" aria-hidden="true">
            <img src="/icons/operator-agents-5f8e38bca670-192.png" width={38} height={38} alt="" />
          </span>
          <span>
            Crypto AI <b>Terminal</b>
            <small>Infrastructure de recherche</small>
          </span>
        </Link>
        <span className="app-current">
          {active?.label ?? "Exploration"}
        </span>
        <span className="app-readonly">Lecture seule</span>
        <AppearanceSettings />
      </header>
      <aside
        id="module-sidebar"
        className={`app-sidebar ${menuOpen ? "is-open" : ""}`}
      >
        <p className="sidebar-label">ESPACE DE RECHERCHE</p>
        <nav aria-label="Modules de la machine">
          {MODULES.map((m) => (
            <NavLink
              key={m.to}
              to={m.to}
              end={m.testId === "tab-overview"}
              data-testid={m.testId}
              aria-current={m.testId === "tab-overview" ? false : "page"}
              className={({ isActive }) =>
                `module-link ${(isActive && m.testId !== "tab-overview") || (m.to.endsWith("/portfolio") && (pathname.endsWith("/lifecycle") || pathname.endsWith("/order-history"))) ? "is-active" : ""}`
              }
            >
              <AppIcon name={m.icon} />
              <span>{m.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span>Observer. Comprendre. Rechercher.</span>
          <small>Les sources gardent leur propre date et leur autorité.</small>
        </div>
      </aside>
      <main className="app-content" id="app-content" tabIndex={-1}>
        <Outlet />
      </main>
      <footer className="app-footer">
        Crypto AI Terminal{" "}
        <span>Présentation passive · aucune commande d’exécution</span>
      </footer>
    </div>
  );
};
