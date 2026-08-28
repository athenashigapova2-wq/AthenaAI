import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { loadEnv } from "vite";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const androidDir = path.join(root, "android");
const npmCli = process.env.npm_execpath;
const capacitorCli = path.join(root, "node_modules", "@capacitor", "cli", "bin", "capacitor");
const apk = path.join(androidDir, "app", "build", "outputs", "apk", "debug", "app-debug.apk");
const forbiddenHosts = new Set(["localhost", "127.0.0.1", "0.0.0.0", "10.0.2.2"]);

function fail(message) {
  console.error(`Android APK build refused: ${message}`);
  process.exit(1);
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd || root,
    env: options.env || process.env,
    encoding: "utf8",
    stdio: "inherit",
  });
  if (result.error) fail(`${command} could not start: ${result.error.message}`);
  if (result.status !== 0) process.exit(result.status ?? 1);
}

function bundledText(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const item = path.join(directory, entry.name);
    if (entry.isDirectory()) return bundledText(item);
    return /\.(?:html|js|json)$/i.test(entry.name) ? fs.readFileSync(item, "utf8") : [];
  }).join("\n");
}

function javaMajor(javaHome) {
  if (!javaHome) return 0;
  const executable = path.join(javaHome, "bin", process.platform === "win32" ? "java.exe" : "java");
  if (!fs.existsSync(executable)) return 0;
  const result = spawnSync(executable, ["-version"], { encoding: "utf8" });
  const versionText = `${result.stdout || ""}\n${result.stderr || ""}`;
  const match = versionText.match(/version\s+"(?:1\.)?(\d+)/);
  return match ? Number(match[1]) : 0;
}

const javaCandidates = [
  path.join(root, ".jdk", "temurin-21"),
  process.platform === "win32" ? "C:\\Program Files\\Android\\Android Studio\\jbr" : "",
  process.env.JAVA_HOME,
].filter(Boolean);
const javaHome = javaCandidates.find((candidate) => javaMajor(candidate) >= 21);

const env = loadEnv("production", root, "");
const rawBackendUrl = process.env.VITE_AGENT_API_URL || env.VITE_AGENT_API_URL || "";
const rawSupabaseUrl = process.env.VITE_SUPABASE_URL || env.VITE_SUPABASE_URL || "";
const supabaseAnonKey = process.env.VITE_SUPABASE_ANON_KEY || env.VITE_SUPABASE_ANON_KEY || "";
let backendUrl;
let supabaseUrl;
try {
  backendUrl = new URL(rawBackendUrl);
} catch {
  fail("set VITE_AGENT_API_URL to the public FastAPI HTTPS origin");
}
try {
  supabaseUrl = new URL(rawSupabaseUrl);
} catch {
  fail("set VITE_SUPABASE_URL to the public Supabase HTTPS origin");
}
if (backendUrl.protocol !== "https:") fail("VITE_AGENT_API_URL must use HTTPS");
if (forbiddenHosts.has(backendUrl.hostname)) fail("local/emulator backend URLs are forbidden");
if (backendUrl.pathname !== "/" || backendUrl.search || backendUrl.hash) {
  fail("VITE_AGENT_API_URL must contain only the backend origin, without a path or query");
}
if (supabaseUrl.protocol !== "https:" || forbiddenHosts.has(supabaseUrl.hostname)) {
  fail("VITE_SUPABASE_URL must be a public HTTPS origin");
}
if (!supabaseAnonKey) fail("VITE_SUPABASE_ANON_KEY is required");

const apiOrigin = backendUrl.origin;
console.log(`Building Android debug APK for ${apiOrigin}`);

if (process.env.SKIP_BACKEND_PREFLIGHT !== "1") {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15_000);
  try {
    const response = await fetch(`${apiOrigin}/health/ready`, { signal: controller.signal });
    const body = await response.json().catch(() => null);
    if (!response.ok || body?.status !== "ready") {
      fail(`backend readiness failed (${response.status}): ${JSON.stringify(body)}`);
    }

    const corsResponse = await fetch(`${apiOrigin}/api/v1/agent/chat`, {
      method: "OPTIONS",
      headers: {
        Origin: "https://localhost",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type,idempotency-key",
      },
      signal: controller.signal,
    });
    if (
      !corsResponse.ok ||
      corsResponse.headers.get("access-control-allow-origin") !== "https://localhost"
    ) {
      fail("backend CORS does not allow the Capacitor origin https://localhost");
    }
  } catch (error) {
    fail(`cannot reach ${apiOrigin}/health/ready: ${error.message}`);
  } finally {
    clearTimeout(timeout);
  }
}

const buildEnv = {
  ...process.env,
  VITE_AGENT_API_URL: apiOrigin,
  VITE_SUPABASE_URL: supabaseUrl.origin,
  VITE_SUPABASE_ANON_KEY: supabaseAnonKey,
};
if (!npmCli) fail("run this script through npm run android:apk");
run(process.execPath, [npmCli, "run", "build"], { env: buildEnv });

const bundle = bundledText(path.join(root, "dist"));
for (const forbidden of ["http://127.0.0.1", "http://10.0.2.2", "localhost:8001"]) {
  if (bundle.includes(forbidden)) fail(`web bundle still contains ${forbidden}`);
}
if (!bundle.includes(apiOrigin)) fail("the HTTPS backend origin is absent from the web bundle");

run(process.execPath, [capacitorCli, "sync", "android"], { env: buildEnv });
if (!javaHome) {
  fail("JDK 21+ is required; install it or place a portable JDK in .jdk/temurin-21");
}
const gradleCommand = process.platform === "win32" ? (process.env.ComSpec || "cmd.exe") : "./gradlew";
const gradleArgs = process.platform === "win32"
  ? ["/d", "/s", "/c", "gradlew.bat assembleDebug --no-daemon --max-workers=1"]
  : ["assembleDebug", "--no-daemon", "--max-workers=1"];
run(gradleCommand, gradleArgs, {
  cwd: androidDir,
  env: {
    ...buildEnv,
    JAVA_HOME: javaHome,
    GRADLE_USER_HOME: process.env.GRADLE_USER_HOME || path.join(os.homedir(), ".gradle"),
  },
});

if (!fs.existsSync(apk)) fail("Gradle completed but the debug APK was not found");
console.log(`APK ready: ${apk}`);
