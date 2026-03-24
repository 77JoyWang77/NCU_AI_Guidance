/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#f0f4f8',
          100: '#d9e2ec',
          200: '#bcccdc',
          300: '#9fb3c8',
          400: '#829ab1',
          500: '#627d98',
          600: '#486581',
          700: '#334e68',
          800: '#243b53',
          900: '#102a43',
        },
        accent: {
          50: '#fff8e6',
          100: '#ffe9b3',
          200: '#ffd980',
          300: '#ffc94d',
          400: '#ffb81a',
          500: '#e69900',
          600: '#b37700',
          700: '#805500',
          800: '#4d3300',
          900: '#1a1100',
        }
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Microsoft JhengHei', 'sans-serif'],
      },
      boxShadow: {
        'soft': '0 2px 8px rgba(0, 0, 0, 0.04)',
        'medium': '0 4px 12px rgba(0, 0, 0, 0.08)',
        'strong': '0 8px 24px rgba(0, 0, 0, 0.12)',
      },
    },
  },
  plugins: [],
}
