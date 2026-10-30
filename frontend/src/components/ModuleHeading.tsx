import React from "react";
export const ModuleHeading: React.FC<{
  title: string;
  description: string;
  badge?: React.ReactNode;
}> = ({ title, description, badge }) => (
  <header className="module-heading">
    <div>
      <p className="section-kicker">CRYPTO AI TERMINAL</p>
      <h1>{title}</h1>
      <p>{description}</p>
    </div>
    {badge}
  </header>
);
