import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: "#0F172A",
        surface: "#111827",
        panel: "#172033",
        accent: "#F97316",
        accentSoft: "#FED7AA",
        success: "#22C55E",
        warning: "#F59E0B",
        danger: "#EF4444",
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "ui-sans-serif", "system-ui"],
      },
      boxShadow: {
        panel: "0 20px 50px rgba(15, 23, 42, 0.35)",
      },
      backgroundImage: {
        grid: "linear-gradient(rgba(255,255,255,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.08) 1px, transparent 1px)"
      }
    },
  },
  plugins: [],
};

export default config;
