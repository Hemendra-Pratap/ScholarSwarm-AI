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
            DEFAULT: 'rgb(var(--brand-navy) / <alpha-value>)',
            dark: 'rgb(var(--brand-navy-dark) / <alpha-value>)',
            light: 'rgb(var(--brand-navy-light) / <alpha-value>)',
          },
          indigo: {
            DEFAULT: 'rgb(var(--brand-indigo) / <alpha-value>)',
            hover: 'rgb(var(--brand-indigo-hover) / <alpha-value>)',
            subtle: 'rgb(var(--brand-indigo-subtle) / <alpha-value>)',
          },
          teal: {
            DEFAULT: 'rgb(var(--brand-teal) / <alpha-value>)',
            hover: 'rgb(var(--brand-teal-hover) / <alpha-value>)',
            subtle: 'rgb(var(--brand-teal-subtle) / <alpha-value>)',
          },
          emerald: {
            DEFAULT: 'rgb(var(--brand-emerald) / <alpha-value>)',
            subtle: 'rgb(var(--brand-emerald-subtle) / <alpha-value>)',
          },
          amber: {
            DEFAULT: 'rgb(var(--brand-amber) / <alpha-value>)',
            subtle: 'rgb(var(--brand-amber-subtle) / <alpha-value>)',
          },
        },
        surface: {
          warm: 'rgb(var(--surface-warm) / <alpha-value>)',
          card: 'rgb(var(--surface-card) / <alpha-value>)',
          muted: 'rgb(var(--surface-muted) / <alpha-value>)',
          border: 'rgb(var(--surface-border) / <alpha-value>)',
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
