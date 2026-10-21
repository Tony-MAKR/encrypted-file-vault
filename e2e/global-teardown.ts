import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

export default async function globalTeardown(): Promise<void> {
  const dataDir = process.env.VAULT_E2E_DATA_DIR
  if (!dataDir) {
    return
  }
  const resolved = path.resolve(dataDir)
  const tempRoot = path.resolve(os.tmpdir())
  if (resolved === tempRoot || !resolved.startsWith(tempRoot + path.sep)) {
    // Never remove anything outside the temporary directory.
    return
  }
  // Windows may keep the database/log files locked for a moment after the
  // web server is stopped. Retry briefly; never remove anything outside temp.
  for (let attempt = 0; attempt < 8; attempt += 1) {
    try {
      fs.rmSync(resolved, { recursive: true, force: true })
      return
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 750))
    }
  }
  console.warn(`Could not remove temporary E2E directory: ${resolved}`)
}
