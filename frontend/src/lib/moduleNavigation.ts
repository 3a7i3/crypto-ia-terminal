import type { IconName } from "../components/AppIcon";

export const MODULES: {
  to: string;
  label: string;
  description: string;
  icon: IconName;
  testId: string;
}[] = [
  {
    to: "/direction",
    label: "Accueil",
    description: "Les sources de ton infrastructure",
    icon: "home",
    testId: "tab-overview",
  },
  {
    to: "/paper-live/market",
    label: "Marché",
    description: "Observations, scanner et liquidité",
    icon: "market",
    testId: "tab-market",
  },
  {
    to: "/paper-live/decisions",
    label: "Décisions",
    description: "Signaux, refus et explications",
    icon: "decisions",
    testId: "tab-decisions",
  },
  {
    to: "/paper-live/portfolio",
    label: "Positions",
    description: "Positions observées et cycle de vie",
    icon: "positions",
    testId: "tab-paper",
  },
  {
    to: "/paper-live/finance",
    label: "Finance",
    description: "Montants, frais et réconciliation",
    icon: "finance",
    testId: "tab-finance",
  },
  {
    to: "/research",
    label: "Laboratoire",
    description: "Évaluations, preuves et stratégies",
    icon: "research",
    testId: "tab-research",
  },
  {
    to: "/paper-live/system",
    label: "Système",
    description: "Services et ressources observés",
    icon: "system",
    testId: "tab-system",
  },
];
