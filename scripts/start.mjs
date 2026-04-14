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

console.log("\nStarting FundOps on http://localhost:8000\n");

const server = spawn(
  join(ROOT, ".venv", "bin", "uvicorn"),
  ["backend.api:app", "--host", "0.0.0.0", "--port", "8000"],
  { cwd: ROOT, stdio: "inherit", env: { ...process.env } }
);

server.on("close", (code) => process.exit(code));

process.on("SIGINT", () => {
  server.kill("SIGINT");
  process.exit(0);
});
