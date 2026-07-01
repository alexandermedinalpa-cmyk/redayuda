/* Config para compilar Tailwind a un CSS estático auto-hospedado (resiste
 * bloqueos del CDN en Venezuela). Replica el tema monocromático de tw-config.js. */
const MONO = {
  DEFAULT: "#121212", 50: "#f7f7f7", 100: "#ededed", 200: "#e0e0e0", 300: "#cfcfcf",
  400: "#767676", 500: "#4a4a4a", 600: "#292929", 700: "#292929", 800: "#1c1c1c",
  900: "#121212", 950: "#121212",
};
const RED = {
  DEFAULT: "#d32f2f", 50: "#fdecea", 100: "#f9d2cd", 200: "#f3b4ad", 300: "#e88a80",
  400: "#dd5c4e", 500: "#d32f2f", 600: "#c62828", 700: "#b71c1c", 800: "#9f1717",
  900: "#7f1414", 950: "#5f0f0f",
};
module.exports = {
  content: ["./static/**/*.html", "./static/**/*.js"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["'Space Grotesk'", "system-ui", "sans-serif"],
        mono: ["'Space Grotesk'", "ui-monospace", "monospace"],
      },
      letterSpacing: { tightest: "-0.03em", tighter: "-0.02em" },
      colors: {
        brand: MONO, slate: MONO, gray: MONO, zinc: MONO, neutral: MONO, stone: MONO,
        emerald: MONO, teal: MONO, sky: MONO, blue: MONO, indigo: MONO,
        violet: MONO, purple: MONO, amber: MONO, yellow: MONO, orange: MONO, green: MONO,
        rose: RED, red: RED, ink: MONO,
      },
      borderRadius: {
        none: "0", sm: "0", DEFAULT: "0", md: "0", lg: "0",
        xl: "0", "2xl": "0", "3xl": "0", full: "0",
      },
    },
  },
};
