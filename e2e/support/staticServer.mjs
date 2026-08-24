import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { build } from "vite";

await build({ configLoader: "runner" });

const root = join(process.cwd(), "dist");
const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".webp": "image/webp",
};

const server = createServer((request, response) => {
  const pathname = decodeURIComponent(new URL(request.url, "http://127.0.0.1").pathname);
  const relativePath = pathname.replace(/^[/\\]+/, "");
  const candidate = normalize(join(root, relativePath));
  const safeCandidate = candidate.startsWith(root) ? candidate : join(root, "index.html");
  const file = existsSync(safeCandidate) && statSync(safeCandidate).isFile()
    ? safeCandidate
    : join(root, "index.html");
  response.writeHead(200, {
    "Content-Type": contentTypes[extname(file)] || "application/octet-stream",
    "Cache-Control": "no-store",
  });
  createReadStream(file).pipe(response);
}).listen(4174, "127.0.0.1", () => {
  process.stdout.write("Athena E2E server ready on http://127.0.0.1:4174\n");
});

const shutdown = () => {
  server.closeAllConnections?.();
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 1_000);
};
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
