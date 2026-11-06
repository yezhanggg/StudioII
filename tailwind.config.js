/** Studio style (Final Two School/_doc/Style): Indigo carries the interface, five light colours the data. */
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Proxima Nova"', '"proxima-nova"', '"DM Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['"Proxima Nova"', '"proxima-nova"', '"DM Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      colors: {
        accent: {
          50: '#f1f1f7', 100: '#dfdfec', 200: '#c3c2db', 300: '#9e9dc2', 400: '#7776a3',
          500: '#545384', 600: '#393864', 700: '#2e2d52', 800: '#232240', 900: '#17162b',
        },
        ink: { DEFAULT: '#1E1E1C', 2: '#57564E', muted: '#8C8A7C' },
      },
    },
  },
  plugins: [],
};
