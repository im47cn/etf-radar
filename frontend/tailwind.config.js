/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        signal: {
          resonance: '#2563EB',
          transmission: '#2563EB',
          divergence: '#EA580C',
        },
      },
    },
  },
  plugins: [],
};
