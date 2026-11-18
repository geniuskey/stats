import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";

export default defineConfig({
  site: process.env.SITE_URL || "https://stats.euiyun.com",
  base: process.env.BASE_PATH || "/",
  trailingSlash: "always",
  outDir: process.env.OUT_DIR || "./dist",
  cacheDir: process.env.CACHE_DIR || "./node_modules/.astro",
  build: { format: "directory" },
  integrations: [sitemap()],
});
