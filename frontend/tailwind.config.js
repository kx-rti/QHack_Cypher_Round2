/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        obsidian: "#0B0D0C",
        charcoal: { DEFAULT: "#121614", hover: "#171C19" },
        acid: { DEFAULT: "#C4F135", hover: "#D4FF47", muted: "rgba(196, 241, 53, 0.30)" },
        "cyber-cyan": "#38BDF8",
        "cyber-amber": "#FACC15",
        "cyber-coral": "#F87171",
        ink: { DEFAULT: "#FFFFFF", body: "#D1D5DB", muted: "#8B948F" },
      },
      fontFamily: {
        display: ["'Space Grotesk'", "sans-serif"],
        sans: ["Inter", "sans-serif"],
        mono: ["'JetBrains Mono'", "monospace"],
      },
      boxShadow: { glow: "0 0 20px rgba(196, 241, 53, 0.12)" },
    },
  },
  plugins: [],
};
