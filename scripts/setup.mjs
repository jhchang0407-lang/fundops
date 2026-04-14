#!/usr/bin/env node
/**
 * FundOps setup — runs automatically on `npm install`.
 * Creates Python venv, installs backend deps, installs frontend deps.
 */
import { execSync } from "child_process";
import { existsSync, writeFileSync, copyFileSync } from "fs";
import { join } from "path";

const ROOT = join(import.meta.dirname, "..");
const run = (cmd, opts = {}) => {
  console.log(`  $ ${cmd}`);
  execSync(cmd, { cwd: ROOT, stdio: "inherit", ...opts });
};

console.log("\n⚙️  Setting up FundOps...\n");

// 1. Python venv + backend deps
const venv = join(ROOT, ".venv");
const python = existsSync(venv)
  ? join(venv, "bin", "python3")
  : null;

if (!existsSync(venv)) {
  console.log("→ Creating Python virtual environment...");
  // Try python3 first, fall back to python
  try {
    run("python3 -m venv .venv");
  } catch {
    run("python -m venv .venv");
  }
}

console.log("→ Installing Python dependencies...");
run(".venv/bin/pip install -q -e '.[dev]'");

// 2. Frontend deps
console.log("→ Installing frontend dependencies...");
run("npm install", { cwd: join(ROOT, "frontend") });

// 3. Build frontend
console.log("→ Building frontend...");
run("npm run build", { cwd: join(ROOT, "frontend") });

// 4. Create .env if missing
const envPath = join(ROOT, ".env");
const envExample = join(ROOT, ".env.example");
if (!existsSync(envPath) && existsSync(envExample)) {
  console.log("→ Creating .env from .env.example...");
  copyFileSync(envExample, envPath);
  console.log("  ⚠️  Edit .env to add your OPENAI_API_KEY before starting.");
}

console.log("\n✅ Setup complete! Run: npm start\n");
