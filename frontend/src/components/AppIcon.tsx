import React from "react";

export type IconName =
  | "home"
  | "market"
  | "decisions"
  | "positions"
  | "finance"
  | "research"
  | "system"
  | "settings"
  | "menu"
  | "close"
  | "project"
  | "arrow"
  | "sun"
  | "moon";
const paths: Record<IconName, React.ReactNode> = {
  home: (
    <>
      <path d="m3 10 9-7 9 7v10H3Z" />
      <path d="M9 20v-7h6v7" />
    </>
  ),
  market: (
    <>
      <path d="M4 3v17h17M7 15l4-5 4 2 5-7" />
    </>
  ),
  decisions: (
    <>
      <path d="M5 4h14v17H5zM8 9h8M8 13h5M8 17h8" />
    </>
  ),
  positions: (
    <>
      <rect x="3" y="7" width="18" height="14" rx="2" />
      <path d="M8 7V3h8v4M3 12h18M10 12v3h4v-3" />
    </>
  ),
  finance: (
    <>
      <path d="m3 8 9-5 9 5M3 21h18M5 11v7M10 11v7M15 11v7M20 11v7" />
    </>
  ),
  research: (
    <>
      <path d="M9 3h6M10 3v7L4 20h16l-6-10V3M7 15h10" />
    </>
  ),
  system: (
    <>
      <rect x="3" y="3" width="18" height="7" rx="2" />
      <rect x="3" y="14" width="18" height="7" rx="2" />
      <path d="M7 6.5h.01M7 17.5h.01M11 6.5h6M11 17.5h6" />
    </>
  ),
  settings: (
    <>
      <path d="m9 3-.6 3-2 .9L3.8 6 2 9l2.3 2v2L2 15l1.8 3 2.6-.9 2 .9L9 21h6l.6-3 2-.9 2.6.9 1.8-3-2.3-2v-2L22 9l-1.8-3-2.6.9-2-.9L15 3Z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  menu: <path d="M4 6h16M4 12h16M4 18h16" />,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  project: (
    <>
      <path d="M3 7h7l2 2h9v12H3ZM3 7V4h7l2 3" />
    </>
  ),
  arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
  sun: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 1v2M12 21v2M1 12h2M21 12h2M4 4l2 2M18 18l2 2M4 20l2-2M18 6l2-2" />
    </>
  ),
  moon: <path d="M21 13A9 9 0 0 1 11 3a9 9 0 1 0 10 10Z" />,
};
export const AppIcon: React.FC<{ name: IconName; size?: number }> = ({
  name,
  size = 20,
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    {paths[name]}
  </svg>
);
