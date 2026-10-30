import React, { useEffect, useRef, useState } from "react";
import { AppIcon } from "./AppIcon";
import {
  applyTheme,
  readTheme,
  saveTheme,
  THEME_KEY,
  type Theme,
} from "../lib/theme";

export const AppearanceSettings: React.FC = () => {
  const [theme, setTheme] = useState<Theme>(readTheme);
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState(true);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);
  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key === THEME_KEY || event.key === null) setTheme(readTheme());
    };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);
  useEffect(() => {
    if (!open) return;
    const outside = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const escape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
  function change(next: Theme) {
    setTheme(next);
    setSaved(saveTheme(next));
  }
  return (
    <div className="appearance-settings" ref={root}>
      <button
        className="icon-button"
        ref={trigger}
        aria-label="Paramètres de l’application"
        aria-expanded={open}
        aria-controls="appearance-panel"
        onClick={() => setOpen(!open)}
        title="Paramètres d’affichage"
      >
        <AppIcon name="settings" />
      </button>
      {open && (
        <section
          className="appearance-panel"
          id="appearance-panel"
          aria-labelledby="appearance-heading"
        >
          <div className="appearance-heading">
            <h2 id="appearance-heading">Apparence</h2>
            <button
              className="icon-button"
              aria-label="Fermer les paramètres"
              onClick={() => {
                setOpen(false);
                trigger.current?.focus();
              }}
            >
              <AppIcon name="close" size={16} />
            </button>
          </div>
          <p>Ton espace de recherche, à ton rythme.</p>
          <fieldset>
            <legend>Thème de l’application</legend>
            {(["light", "dark"] as const).map((value) => (
              <label
                key={value}
                className={`theme-choice ${theme === value ? "selected" : ""}`}
              >
                <input
                  type="radio"
                  name="appearance-theme"
                  value={value}
                  checked={theme === value}
                  onChange={() => change(value)}
                />
                <span
                  className={`theme-preview theme-preview-${value}`}
                  aria-hidden="true"
                >
                  <i />
                  <i />
                  <i />
                </span>
                <span>
                  <AppIcon
                    name={value === "light" ? "sun" : "moon"}
                    size={16}
                  />
                  {value === "light" ? "Clair" : "Sombre"}
                </span>
              </label>
            ))}
          </fieldset>
          <p className="settings-note" role="status">
            {saved
              ? "Choix mémorisé sur cet appareil. Aucun effet sur la machine."
              : "Stockage du navigateur indisponible : choix appliqué pour cette session."}
          </p>
        </section>
      )}
    </div>
  );
};
