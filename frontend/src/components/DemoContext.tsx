import { createContext, useContext } from "react";
import type { ReactNode } from "react";

// Default production has no demo data. Only the separate demo entry provides this.
export const DemoContext = createContext<ReactNode>(null);
export const useDemoCharts = () => useContext(DemoContext);
