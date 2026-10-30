import process from "node:process";

import { loadEnv } from "vite";

const env = {
  ...loadEnv("production", process.cwd(), ""),
  ...process.env,
};

function requiredHttpsUrl(name) {
  const value = env[name]?.trim();
  if (!value) throw new Error(`${name} is required for a web deployment`);

  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`${name} must be a valid absolute URL`);
  }
  if (url.protocol !== "https:") throw new Error(`${name} must use HTTPS`);
  if (["localhost", "127.0.0.1", "::1"].includes(url.hostname)) {
    throw new Error(`${name} must not point to localhost`);
  }
}

requiredHttpsUrl("VITE_SUPABASE_URL");
requiredHttpsUrl("VITE_AGENT_API_URL");

if (!env.VITE_SUPABASE_ANON_KEY?.trim()) {
  throw new Error("VITE_SUPABASE_ANON_KEY is required for a web deployment");
}

console.log("Web deployment environment is valid");
