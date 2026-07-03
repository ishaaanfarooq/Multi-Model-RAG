import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
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
          DEFAULT: "#2A2318",
          light: "#4A4033",
        },
        stone: {
          50: "#FAF8F4",
          400: "#A79C87",
          500: "#8A8171",
          600: "#6B6455",
        },
        cream: {
          50: "#FEFDFA",
          100: "#F7F2E7",
          200: "#F0E8D6",
          300: "#E3D8C1",
          400: "#D2C3A5",
        },
        brass: {
          50: "#FAF3E6",
          100: "#F2E2C0",
          200: "#E6CB98",
          300: "#D4AD68",
          400: "#C0924A",
          500: "#A97A3A",
          600: "#8F6530",
          700: "#6E4E26",
          800: "#54391C",
          900: "#3D2814",
        },
        sage: {
          50: "#EEF4EC",
          100: "#DCE9D7",
          500: "#4C7A52",
          700: "#3A5D40",
        },
        brick: {
          50: "#FBEDEB",
          100: "#F5D9D4",
          500: "#B0463E",
          700: "#8A362F",
        },
      },
      fontFamily: {
        serif: ["var(--font-display)", "Georgia", "serif"],
        sans: ["var(--font-body)", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
export default config;
