/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef4ff',
          100: '#dbe5ff',
          500: '#4f6df5',
          600: '#3b56db',
          700: '#2f44b0',
        },
      },
    },
  },
  plugins: [],
};
