/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // AskCell accent palette — chrome/UI only. Data-encoding colors (scatter
        // points, chart series/bars) are NOT drawn from these; see lib/viz.js
        // for the validated categorical/status palette used there instead.
        indigo: {
          400: "#818cf8",
          500: "#6366f1",
          600: "#4f46e5",
        },
        emerald: {
          400: "#34d399",
          500: "#10b981",
        },
        violet: {
          400: "#a78bfa",
          500: "#8b5cf6",
          600: "#7c3aed",
        },
        fuchsia: {
          400: "#e879f9",
          500: "#d946ef",
          600: "#c026d3",
        },
        cyan: {
          400: "#22d3ee",
          500: "#06b6d4",
          600: "#0891b2",
        },
        amber: {
          400: "#fbbf24",
          500: "#f59e0b",
          600: "#d97706",
        },
      },
      fontFamily: {
        sans: ['"Space Grotesk"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      backgroundImage: {
        // Diagonal brand gradient — hero text, active states, primary CTAs.
        "brand-gradient": "linear-gradient(135deg, #6366f1 0%, #8b5cf6 40%, #d946ef 75%, #22d3ee 100%)",
        // Softer version for tinted panel washes / hover fills.
        "brand-gradient-soft": "linear-gradient(135deg, rgba(99,102,241,0.16) 0%, rgba(217,70,239,0.12) 60%, rgba(34,211,238,0.14) 100%)",
      },
      backgroundSize: {
        200: "200% 200%",
      },
      boxShadow: {
        "glow-violet": "0 0 24px -4px rgba(139,92,246,0.55)",
        "glow-cyan": "0 0 24px -4px rgba(34,211,238,0.5)",
        "glow-rose": "0 0 24px -4px rgba(224,80,80,0.5)",
        "glow-emerald": "0 0 24px -4px rgba(16,185,129,0.45)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-dot": {
          "0%, 100%": { opacity: "0.4" },
          "50%": { opacity: "1" },
        },
        "gradient-shift": {
          "0%, 100%": { backgroundPosition: "0% 50%" },
          "50%": { backgroundPosition: "100% 50%" },
        },
        "glow-pulse": {
          "0%, 100%": { boxShadow: "0 0 0px rgba(139,92,246,0)" },
          "50%": { boxShadow: "0 0 22px rgba(139,92,246,0.6)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.28s ease-out",
        "pulse-dot": "pulse-dot 1.2s ease-in-out infinite",
        "gradient-shift": "gradient-shift 6s ease infinite",
        "glow-pulse": "glow-pulse 2.2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
