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
    rollupOptions: {
      output: {
        manualChunks(id) {
          // Pro Components 3.x 内部存在跨 barrel 的循环依赖；整包落入同一共享 chunk，
          // 避免按页面动态拆分时出现执行顺序警告，同时让所有管理页复用缓存。
          const normalizedId = id.replaceAll("\\", "/");
          if (normalizedId.includes("@ant-design+pro-components") || normalizedId.includes("/@ant-design/pro-components/")) return "pro-components";
          if (normalizedId.includes("@ant-design+icons") || normalizedId.includes("/antd/")) return "antd";
          return undefined;
        },
      },
    },
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
