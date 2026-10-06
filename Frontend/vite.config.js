import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    // Use a browser-like DOM so React components can mount and be queried.
    // happy-dom instead of jsdom keeps the dependency tree (and lockfile) smaller.
    environment: "happy-dom",
    // Allow describe/it/expect to be used without importing them in every file.
    globals: true,
    // Runs once before each test file — wires up jest-dom matchers and mocks.
    setupFiles: "./tests/setup.js",
  },
});
