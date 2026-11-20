import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    // File events don't reach the container through Docker-on-Mac bind mounts, so poll.
    watch: { usePolling: true, interval: 300 },
  },
});
