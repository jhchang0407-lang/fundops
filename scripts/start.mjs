#!/usr/bin/env node
/**
 * FundOps start — launches backend + frontend with one command.
 * Backend serves the built frontend, so only one server is needed.
 */
import { spawn } from "child_process";
import { existsSync } from "fs";
import { join } from "path";

const ROOT = join(import.meta.dirname, "..");

// Check setup
if (!existsSync(join(ROOT, ".venv"))) {
  console.error("❌ Run `npm install` first to set up the project.");
  process.exit(1);
}

const envPath = join(ROOT, ".env");
if (!existsSync(envPath)) {
  console.error("❌ Missing .env file. Copy .env.example to .env and add your API keys.");
  process.exit(1);
}

// Check if OPENAI_API_KEY is set
import { readFileSync } from "fs";
const envContent = readFileSync(envPath, "utf-8");
if (envContent.includes("your_openai_api_key_here")) {
  console.warn("⚠️  OPENAI_API_KEY not set in .env — AI agents won't work until you add it.");
}

console.log("\n🚀 Starting FundOps on http://localhost:8000\n");

const server = spawn(
  join(ROOT, ".venv", "bin", "uvicorn"),
  ["backend.api:app", "--host", "0.0.0.0", "--port", "8000"],
  { cwd: ROOT, stdio: "inherit", env: { ...process.env } }
);

server.on("close", (code) => process.exit(code));

// Handle Ctrl+C
process.on("SIGINT", () => {
  server.kill("SIGINT");
  process.exit(0);
});
