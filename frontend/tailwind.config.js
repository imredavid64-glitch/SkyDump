/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        slate: {
          950: '#020617',
          900: '#0f172a',
          850: '#162038',
          800: '#1e293b',
        },
        emerald: {
          500: '#10b981',
          400: '#34d399',
          600: '#059669',
        },
        amber: {
          500: '#f59e0b',
          400: '#fbbf24',
        },
        red: {
          500: '#ef4444',
          400: '#f87171',
        }
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'spin-slow': 'spin 2s linear infinite',
      }
    },
  },
  plugins: [],
}