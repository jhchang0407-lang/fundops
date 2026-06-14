#!/usr/bin/env node
import { existsSync, rmSync } from 'node:fs';
import { join } from 'node:path';

const fseventsPath = join(import.meta.dirname, '..', 'node_modules', 'fsevents');

if (process.platform === 'darwin' && existsSync(fseventsPath)) {
  rmSync(fseventsPath, { recursive: true, force: true });
  console.log('Removed optional fsevents native watcher; Vite will use the portable watcher.');
}
