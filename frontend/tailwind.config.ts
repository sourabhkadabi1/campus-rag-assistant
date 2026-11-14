import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        card: {
          DEFAULT: "var(--card)",
          foreground: "var(--card-foreground)",
        },
        primary: {
          DEFAULT: "var(--primary)",
          foreground: "var(--primary-foreground)",
          50: "var(--color-accent)", 100: "var(--color-accent)", 200: "var(--color-accent)",
          300: "var(--color-accent)", 400: "var(--color-accent)", 500: "var(--color-accent)",
          600: "var(--color-accent)", 700: "var(--color-accent)", 800: "var(--color-accent)", 900: "var(--color-accent)",
        },
        secondary: {
          DEFAULT: "var(--secondary)",
          foreground: "var(--secondary-foreground)",
        },
        muted: {
          DEFAULT: "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          foreground: "var(--accent-foreground)",
        },
        border: "var(--border)",
        ring: "var(--ring)",
        success: { 300: "var(--color-success)", 400: "var(--color-success)", 500: "var(--color-success)", 600: "var(--color-success)" },
        danger: { 300: "var(--color-error)", 400: "var(--color-error)", 500: "var(--color-error)", 600: "var(--color-error)", 700: "var(--color-error)" },
        code: { 50: "var(--color-code-ink)", 100: "var(--color-code-ink)", 200: "var(--color-ink-2)", 300: "var(--color-muted)", 400: "var(--color-muted)", 500: "var(--color-muted)", 600: "var(--color-ink-2)", 700: "var(--color-code-bg)", 800: "var(--color-code-bg)", 900: "var(--color-code-bg)", 950: "var(--color-code-bg)" },
        amber: { 300: "var(--color-accent)", 400: "var(--color-accent)", 500: "var(--color-accent)", 600: "var(--color-accent)", 700: "var(--color-accent)" },
        purple: { 300: "var(--color-accent)", 400: "var(--color-accent)", 500: "var(--color-accent)", 600: "var(--color-accent)" },
        pink: { 300: "var(--color-accent)", 400: "var(--color-accent)", 500: "var(--color-accent)", 600: "var(--color-accent)" },
        indigo: { 300: "var(--color-accent)", 400: "var(--color-accent)", 500: "var(--color-accent)", 600: "var(--color-accent)" },
        blue: { 300: "var(--color-accent)", 400: "var(--color-accent)", 500: "var(--color-accent)", 600: "var(--color-accent)" },
        emerald: { 300: "var(--color-success)", 400: "var(--color-success)", 500: "var(--color-success)", 600: "var(--color-success)" },
        teal: { 300: "var(--color-success)", 400: "var(--color-success)", 500: "var(--color-success)", 600: "var(--color-success)" },
        red: { 300: "var(--color-error)", 400: "var(--color-error)", 500: "var(--color-error)", 600: "var(--color-error)", 700: "var(--color-error)" },
        slate: { 50: "var(--color-code-ink)", 100: "var(--color-code-ink)", 200: "var(--color-ink-2)", 300: "var(--color-muted)", 400: "var(--color-muted)", 500: "var(--color-muted)", 600: "var(--color-ink-2)", 700: "var(--color-code-bg)", 800: "var(--color-code-bg)", 900: "var(--color-code-bg)", 950: "var(--color-code-bg)" },
        gray: { 200: "var(--color-rule)", 300: "var(--color-rule)", 400: "var(--color-muted)", 500: "var(--color-muted)", 600: "var(--color-ink-2)", 700: "var(--color-ink-2)", 800: "var(--color-paper-2)", 900: "var(--color-paper)" },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        shimmer: {
          "100%": {
            transform: "translateX(100%)",
          },
        },
        pulseGlow: {
          "0%, 100%": { opacity: "0.4", transform: "scale(1)" },
          "50%": { opacity: "0.8", transform: "scale(1.05)" },
        },
      },
      animation: {
        shimmer: "shimmer 2s infinite",
        pulseGlow: "pulseGlow 3s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
export default config;
