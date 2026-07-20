import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  root: "console",
  base: "/console-assets/",
  plugins: [react()],
  build: {
    outDir: "../server/web/console-dist",
    emptyOutDir: true,
    assetsDir: "assets",
  },
  server: {
    port: 8103,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8100",
        changeOrigin: true,
      },
    },
  },
});
