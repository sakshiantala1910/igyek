/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#0b1220',
        panel: '#111a2e',
        edge: '#1f2b45',
        muted: '#8a9ab5',
        wind: '#38bdf8',
        outturn: '#f8fafc',
        short: '#fb7185',
        long: '#34d399',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
}
