import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// base: "./" обязателен — статику отдаёт FastAPI из подпапки, а внутри
// собранного .exe пути тем более не совпадают с корнем сайта
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: { outDir: "dist", emptyOutDir: true },
});
