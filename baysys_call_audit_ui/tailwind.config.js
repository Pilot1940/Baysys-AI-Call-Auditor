/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          wine:       "#9E1B6A",
          "wine-light": "#F5E6EF",
          "wine-dark":  "#7B1553",
        },
      },
    },
  },
  plugins: [],
};
