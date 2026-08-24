import { spawn } from "node:child_process";
import { join } from "node:path";

const root = process.cwd();
const server = spawn(process.execPath, [join(root, "e2e/support/staticServer.mjs")], {
  cwd: root,
  env: {
    ...process.env,
    VITE_SUPABASE_URL: "http://127.0.0.1:54321",
    VITE_SUPABASE_ANON_KEY: "e2e-anon-key",
    VITE_AGENT_API_URL: "http://127.0.0.1:8001",
  },
  stdio: "inherit",
});

const stopServer = () => {
  if (!server.killed) server.kill();
};

process.once("SIGINT", () => {
  stopServer();
  process.exit(130);
});
process.once("SIGTERM", () => {
  stopServer();
  process.exit(143);
});

try {
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    if (server.exitCode !== null) throw new Error(`E2E server exited with code ${server.exitCode}`);
    try {
      const response = await fetch("http://127.0.0.1:4174/login");
      if (response.ok) break;
    } catch {
      // Build and server startup are still in progress.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }

  const response = await fetch("http://127.0.0.1:4174/login").catch(() => null);
  if (!response?.ok) throw new Error("Timed out waiting for the E2E server");

  const cli = join(root, "node_modules/@playwright/test/cli.js");
  const runner = spawn(process.execPath, [cli, "test", ...process.argv.slice(2)], {
    cwd: root,
    env: process.env,
    stdio: "inherit",
  });
  const exitCode = await new Promise((resolve) => runner.once("exit", (code) => resolve(code ?? 1)));
  stopServer();
  process.exit(exitCode);
} catch (error) {
  stopServer();
  console.error(error);
  process.exit(1);
}
