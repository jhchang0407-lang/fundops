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
  console.error("Run `npm install` first to set up the project.");
  process.exit(1);
}

const PORT = process.env.PORT || "8000";
// Localhost by default: the API is single-owner and unauthenticated, so it
// must not listen on the network unless explicitly asked (HOST=0.0.0.0).
const HOST = process.env.HOST || "127.0.0.1";

console.log(`\nStarting FundOps on http://localhost:${PORT}\n`);

// Run uvicorn via the venv python so stale entry-point shebangs (e.g. after
// the repo moves or the venv is copied) can't break startup.
const server = spawn(
  join(ROOT, ".venv", "bin", "python"),
  ["-m", "uvicorn", "backend.api:app", "--host", HOST, "--port", PORT],
  { cwd: ROOT, stdio: "inherit", env: { ...process.env } }
);

server.on("close", (code) => process.exit(code));

process.on("SIGINT", () => {
  server.kill("SIGINT");
  process.exit(0);
});
