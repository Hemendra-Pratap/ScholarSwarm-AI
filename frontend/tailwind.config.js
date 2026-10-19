/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          navy: {
            DEFAULT: '#0b1329',
            dark: '#070c1b',
            light: '#1e293b',
          },
          indigo: {
            DEFAULT: '#4f46e5',
            hover: '#4338ca',
            subtle: '#eef2ff',
          },
          teal: {
            DEFAULT: '#0d9488',
            hover: '#0f766e',
            subtle: '#f0fdfa',
          },
          emerald: {
            DEFAULT: '#059669',
            subtle: '#ecfdf5',
          },
          amber: {
            DEFAULT: '#d97706',
            subtle: '#fffbeb',
          },
        },
        surface: {
          warm: '#fbfbfa',
          card: '#ffffff',
          muted: '#f8fafc',
          border: '#e2e8f0',
        },
      },
      fontFamily: {
        sans: [
          'Inter',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'Roboto',
          'sans-serif',
        ],
        mono: [
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'Monaco',
          'Consolas',
          'monospace',
        ],
      },
    },
  },
  plugins: [],
}
