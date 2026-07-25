import type { Config } from "tailwindcss";

// Colors are driven by CSS variables holding space-separated RGB channels, e.g.
// `--brass-500: 169 122 58`. Wrapping them as `rgb(var(--x) / <alpha-value>)` keeps
// Tailwind's opacity modifiers (bg-brass-500/60) working while letting a single
// `data-theme` flip on <html> re-theme the whole app at runtime.
const c = (v: string) => `rgb(var(${v}) / <alpha-value>)`;

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // `bg-white` is used everywhere as "the panel surface", so route it through a
        // variable too — in HUD mode it becomes a dark panel, and `text-white` on the
        // accent buttons becomes dark-on-neon (an intentional cyberpunk look).
        white: c("--white"),

        background: "var(--color-background)",
        foreground: "var(--color-foreground)",
        surface: "var(--color-surface)",
        "surface-hover": "var(--color-surface-hover)",
        border: "var(--color-border)",
        "border-bright": "var(--color-border-bright)",
        accent: "var(--color-accent)",
        "accent-secondary": "var(--color-accent-secondary)",
        "accent-gradient-from": "var(--color-accent-gradient-from)",
        "accent-gradient-to": "var(--color-accent-gradient-to)",
        muted: "var(--color-muted)",
        success: "var(--color-success)",
        warning: "var(--color-warning)",
        error: "var(--color-error)",
        ink: {
          DEFAULT: c("--ink"),
          light: c("--ink-light"),
        },
        stone: {
          50: c("--stone-50"),
          400: c("--stone-400"),
          500: c("--stone-500"),
          600: c("--stone-600"),
        },
        cream: {
          50: c("--cream-50"),
          100: c("--cream-100"),
          200: c("--cream-200"),
          300: c("--cream-300"),
          400: c("--cream-400"),
        },
        brass: {
          50: c("--brass-50"),
          100: c("--brass-100"),
          200: c("--brass-200"),
          300: c("--brass-300"),
          400: c("--brass-400"),
          500: c("--brass-500"),
          600: c("--brass-600"),
          700: c("--brass-700"),
          800: c("--brass-800"),
          900: c("--brass-900"),
        },
        sage: {
          50: c("--sage-50"),
          100: c("--sage-100"),
          500: c("--sage-500"),
          700: c("--sage-700"),
        },
        brick: {
          50: c("--brick-50"),
          100: c("--brick-100"),
          500: c("--brick-500"),
          700: c("--brick-700"),
        },
      },
      fontFamily: {
        serif: ["var(--font-display)", "Georgia", "serif"],
        sans: ["var(--font-body)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
