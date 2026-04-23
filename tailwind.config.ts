import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // OLED dark base
        base: {
          950: "#09090B",
          900: "#18181B",
          800: "#27272A",
          700: "#3F3F46",
          600: "#52525B",
        },
        // Indigo primary
        primary: {
          300: "#A5B4FC",
          400: "#818CF8",
          500: "#6366F1",
          600: "#4F46E5",
          700: "#4338CA",
        },
        // Emerald CTA
        cta: {
          400: "#34D399",
          500: "#10B981",
          600: "#059669",
        },
        // Status colors
        amber: {
          400: "#FBBF24",
          500: "#F59E0B",
        },
        rose: {
          400: "#FB7185",
          500: "#F43F5E",
        },
      },
      fontFamily: {
        sans: ["Inter", "Fira Sans", "sans-serif"],
        mono: ["Fira Code", "monospace"],
      },
      backgroundImage: {
        "grid-pattern":
          "linear-gradient(rgba(99,102,241,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(99,102,241,0.03) 1px, transparent 1px)",
        "glow-indigo":
          "radial-gradient(ellipse 80% 50% at 50% -20%, rgba(99,102,241,0.3), transparent)",
        "glow-emerald":
          "radial-gradient(ellipse 60% 40% at 50% 100%, rgba(16,185,129,0.15), transparent)",
      },
      backgroundSize: {
        grid: "40px 40px",
      },
      boxShadow: {
        glow: "0 0 20px rgba(99,102,241,0.3)",
        "glow-sm": "0 0 10px rgba(99,102,241,0.2)",
        "glow-cta": "0 0 20px rgba(16,185,129,0.3)",
        card: "0 1px 3px rgba(0,0,0,0.5), 0 1px 2px rgba(0,0,0,0.6)",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4,0,0.6,1) infinite",
        "fade-in": "fadeIn 0.3s ease-out",
        "slide-up": "slideUp 0.4s ease-out",
        "typing": "typing 1.5s steps(30) infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        typing: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
