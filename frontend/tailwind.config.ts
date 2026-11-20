import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "var(--font-noto-sans-tc)",
          "-apple-system",
          "PingFang TC",
          "Microsoft JhengHei",
          "sans-serif",
        ],
      },
      colors: {
        bg: "var(--bg)",
        surface: "var(--card)",
        ink: "var(--ink)",
        muted: "var(--muted)",
        line: "var(--line)",
        chip: "var(--chip)",
        brand: {
          DEFAULT: "var(--brand)",
          2: "var(--brand-2)",
          dark: "var(--brand-dark)",
          soft: "var(--brand-soft)",
          ink: "var(--brand-ink)",
        },
        ok: {
          DEFAULT: "var(--ok)",
          soft: "var(--ok-soft)",
        },
        warn: {
          DEFAULT: "var(--warn)",
          soft: "var(--warn-soft)",
        },
        crit: {
          DEFAULT: "var(--crit)",
          soft: "var(--crit-soft)",
        },
        "line-green": {
          DEFAULT: "var(--line-green)",
          dark: "var(--line-green-dark)",
        },
      },
      boxShadow: {
        card: "var(--shadow)",
        "card-pop": "var(--shadow-pop)",
        hero: "0 10px 24px -6px rgba(255, 107, 53, 0.35)",
        "game-brand": "0 4px 0 0 var(--brand-dark)",
        "game-brand-press": "0 1px 0 0 var(--brand-dark)",
        "game-line": "0 4px 0 0 var(--line-green-dark)",
        "game-neutral": "0 3px 0 0 var(--line)",
      },
      keyframes: {
        "pop-in": {
          "0%": { opacity: "0", transform: "scale(0.95) translateY(6px)" },
          "100%": { opacity: "1", transform: "scale(1) translateY(0)" },
        },
        "badge-bounce": {
          "0%": { transform: "scale(0.6)" },
          "60%": { transform: "scale(1.15)" },
          "100%": { transform: "scale(1)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      animation: {
        "pop-in": "pop-in 0.22s cubic-bezier(0.2, 0.9, 0.3, 1.1) both",
        "badge-bounce": "badge-bounce 0.28s cubic-bezier(0.2, 0.9, 0.3, 1.2) both",
        shimmer: "shimmer 2.2s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
