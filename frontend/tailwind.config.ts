import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: "var(--color-primary)",
        "primary-hover": "var(--color-primary-hover)",
        "on-primary": "var(--color-on-primary)",
        accent: "var(--color-accent)",
        bg: "var(--color-bg)",
        surface: "var(--color-surface)",
        text: "var(--color-text)",
        muted: "var(--color-muted)",
        border: "var(--color-border)",
        danger: "var(--color-danger)",
        tint: "var(--color-tint)",
      },
      fontFamily: {
        sans: "var(--font-sans)",
      },
      borderRadius: {
        DEFAULT: "var(--radius)",
      },
      boxShadow: {
        none: "none",
      },
      minHeight: {
        touch: "var(--touch-min)",
      },
    },
  },
  plugins: [],
} satisfies Config;
