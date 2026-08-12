/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        shark: {
          bg: '#0a0e17',
          card: '#111827',
          border: '#1e293b',
          accent: '#3b82f6',
          'accent-hover': '#2563eb',
          text: '#e2e8f0',
          muted: '#94a3b8',
          success: '#22c55e',
          warning: '#f59e0b',
          danger: '#ef4444',
          info: '#3b82f6',
        }
      }
    },
  },
  plugins: [],
}
