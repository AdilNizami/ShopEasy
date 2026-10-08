import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#17211e",
        muted: "#68736e",
        canvas: "#f7f7f3",
        line: "#e6e9e3",
        green: { 50: "#edf5ed", 100: "#dcebdd", 600: "#39734d", 700: "#285c3b" },
        citrus: "#d8f066",
      },
      fontFamily: {
        sans: ["Arial", "Helvetica", "sans-serif"],
        display: ["Georgia", "Times New Roman", "serif"],
      },
      boxShadow: {
        card: "0 12px 36px rgba(24, 36, 30, .07)",
        float: "0 20px 60px rgba(24, 36, 30, .13)",
      },
    },
  },
  plugins: [],
};

export default config;
