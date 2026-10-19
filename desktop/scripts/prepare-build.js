'use strict'

/**
 * Writes build metadata next to package.json. electron-builder copies it into
 * the packaged application as an extra resource; main.js reads it for the
 * About page. The development build shows "开发模式" instead.
 */

const fs = require('node:fs')
const path = require('node:path')

const root = path.resolve(__dirname, '..')
const packageJson = JSON.parse(
  fs.readFileSync(path.join(root, 'package.json'), 'utf8'),
)
const output = path.join(root, 'dist-build-info.json')

fs.writeFileSync(
  output,
  `${JSON.stringify(
    {
      version: packageJson.version,
      buildTime: new Date().toISOString(),
    },
    null,
    2,
  )}\n`,
  'utf8',
)

console.log(`Build info written to ${output}`)
