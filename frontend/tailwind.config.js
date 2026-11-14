/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        darkBg: "#0B0F19",
        cardBg: "#111827",
        borderCol: "#1F2937",
        accentBlue: "#2563EB",
        accentGlow: "#3B82F6",
      },
    },
  },
  plugins: [],
}