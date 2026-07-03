import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { host: true, port: 5173 },
  preview: { host: true, port: 5173 },
  test: { environment: "node", include: ["src/**/*.test.{ts,tsx}"] },
  build: {
    rollupOptions: {
      output: {
        // Separa las librerías pesadas en chunks propios (cacheables y cargados
        // bajo demanda con el code-splitting por pestaña).
        manualChunks: {
          react: ["react", "react-dom"],
          charts: ["recharts"],
          map: ["leaflet", "react-leaflet"],
        },
      },
    },
  },
});
