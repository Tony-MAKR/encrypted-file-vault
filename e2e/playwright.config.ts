import { defineConfig } from '@playwright/test'
import os from 'node:os'
import path from 'node:path'

// A fixed temporary directory keeps repeated local runs from accumulating
// data. The server script deletes and recreates it before starting.
const dataDir = path.join(os.tmpdir(), 'encrypted-file-vault-e2e')
process.env.VAULT_E2E_DATA_DIR = dataDir

export default defineConfig({
  testDir: './tests',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  globalTeardown: './global-teardown.ts',
  use: {
    baseURL: 'http://127.0.0.1:8020',
    channel: 'msedge',
    headless: true,
    trace: 'off',
    video: 'off',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'powershell -ExecutionPolicy Bypass -File ../scripts/e2e-server.ps1',
    url: 'http://127.0.0.1:8020/api/v1/health/',
    reuseExistingServer: false,
    timeout: 180_000,
    env: {
      ...(process.env as Record<string, string>),
      VAULT_E2E_DATA_DIR: dataDir,
    },
  },
})
