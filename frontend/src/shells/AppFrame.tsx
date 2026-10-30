import React, { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { AppIcon } from "../components/AppIcon";
import { AppearanceSettings } from "../components/AppearanceSettings";
import { MODULES } from "../lib/moduleNavigation";

export const AppFrame: React.FC = () => {
  const { pathname } = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    setMenuOpen(false);
    document.getElementById("app-content")?.focus({ preventScroll: true });
  }, [pathname]);
  const active = MODULES.find(
    (m) =>
      m.to === pathname ||
      (m.to === "/research" && pathname.startsWith("/research/")) ||
      (m.to.endsWith("/portfolio") && pathname.endsWith("/lifecycle")),
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
        <Link className="app-brand" to="/direction">
          <span className="app-brand-symbol" aria-hidden="true">
            <AppIcon name="research" size={23} />
          </span>
          <span>
            Crypto AI <b>Terminal</b>
            <small>Infrastructure de recherche</small>
          </span>
        </Link>
        <span className="app-current">
          {active?.label ??
            (pathname === "/direction/travaux" ? "Projet" : "Exploration")}
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
              end={m.to === "/direction"}
              data-testid={m.testId}
              className={({ isActive }) =>
                `module-link ${isActive || (m.to.endsWith("/portfolio") && pathname.endsWith("/lifecycle")) ? "is-active" : ""}`
              }
            >
              <AppIcon name={m.icon} />
              <span>{m.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-project">
          <span className="sidebar-label">PROJET</span>
          <NavLink
            to="/direction/travaux"
            className={({ isActive }) =>
              `module-link ${isActive ? "is-active" : ""}`
            }
          >
            <AppIcon name="project" />
            <span>Travaux et roadmap</span>
          </NavLink>
        </div>
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
