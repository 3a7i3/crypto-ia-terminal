import React from "react";
import { Outlet } from "react-router-dom";
export const DirectionShell: React.FC = () => (
  <div data-testid="direction-shell">
    <Outlet />
  </div>
);
