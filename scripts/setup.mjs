#!/usr/bin/env node
/**
 * FundOps setup — runs automatically on `npm install`.
 * Creates Python venv, installs backend deps, installs frontend deps.
 */
import { execSync } from "child_process";
import { existsSync } from "fs";
import { join } from "path";

const ROOT = join(import.meta.dirname, "..");
const run = (cmd, opts = {}) => {
  console.log(`  $ ${cmd}`);
  execSync(cmd, { cwd: ROOT, stdio: "inherit", ...opts });
};

console.log("\n⚙️  Setting up FundOps...\n");

// 1. Python venv + backend deps
const venv = join(ROOT, ".venv");

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
run(".venv/bin/python -m pip install -q -e '.[dev]'");

// 1b. Clear macOS Gatekeeper quarantine from native wheels (yfinance's
// curl_cffi and PyYAML's C extension ship dylibs that, when pip downloads
// them through a quarantining browser/proxy, get tagged com.apple.quarantine
// and fail to dlopen — "library load disallowed by system policy"). Harmless
// on non-macOS and when nothing is quarantined.
if (process.platform === "darwin") {
  try {
    console.log("→ Clearing macOS quarantine from native dependencies...");
    execSync("xattr -dr com.apple.quarantine .venv", { cwd: ROOT, stdio: "ignore" });
  } catch {
    /* nothing quarantined, or xattr unavailable — safe to ignore */
  }
}

// 2. Frontend deps
console.log("→ Installing frontend dependencies...");
run("npm install", { cwd: join(ROOT, "frontend") });

// 3. Build frontend
console.log("→ Building frontend...");
run("npm run build", { cwd: join(ROOT, "frontend") });

console.log("\n✅ Setup complete! Run: npm start\n");
