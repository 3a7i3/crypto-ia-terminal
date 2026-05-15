/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Backgrounds
        bg: {
          dark:   "#0f172a",
          card:   "#1e293b",
          hover:  "#334155",
          border: "#334155",
        },
        // Text
        text: {
          pri:  "#f8fafc",
          sec:  "#94a3b8",
          muted:"#475569",
        },
        // Status
        ok:      "#22c55e",
        warn:    "#f59e0b",
        danger:  "#ef4444",
        accent:  "#00e0ff",
        // Regimes
        bull:    "#22c55e",
        bear:    "#ef4444",
        range:   "#6b7280",
        volatile:"#f59e0b",
        // Conviction
        cvh:     "#22c55e",  // VERY_HIGH
        cvhi:    "#84cc16",  // HIGH
        cvm:     "#f59e0b",  // MEDIUM
        cvl:     "#f97316",  // LOW
        cvs:     "#6b7280",  // SKIP
        // Postmortem
        validated:"#22c55e",
        lucky:    "#84cc16",
        unlucky:  "#f59e0b",
        mistake:  "#ef4444",
      },
      fontFamily: {
        mono: ["'JetBrains Mono'", "'Fira Code'", "ui-monospace", "monospace"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      fontSize: {
        "2xs": "0.65rem",
        xs:    "0.75rem",
        sm:    "0.875rem",
      },
      borderRadius: {
        card: "6px",
        badge:"3px",
      },
      boxShadow: {
        card: "0 1px 3px rgba(0,0,0,0.4)",
      },
      animation: {
        pulse_slow: "pulse 3s cubic-bezier(0.4,0,0.6,1) infinite",
        fade_in:    "fadeIn 0.15s ease-out",
      },
      keyframes: {
        fadeIn: {
          "0%":   { opacity: 0, transform: "translateY(-4px)" },
          "100%": { opacity: 1, transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};
