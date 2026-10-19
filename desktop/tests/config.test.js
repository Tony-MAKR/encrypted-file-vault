'use strict'

const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const {
  DEFAULT_HEIGHT,
  DEFAULT_WIDTH,
  MIN_HEIGHT,
  MIN_WIDTH,
  loadConfig,
  saveConfig,
  saveWindowState,
} = require('../src/config')

function temporaryDirectory(t) {
  const directory = fs.mkdtempSync(
    path.join(os.tmpdir(), 'vault-desktop-test-'),
  )
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }))
  return directory
}

test('a missing config produces safe defaults', (t) => {
  const directory = temporaryDirectory(t)
  const config = loadConfig(directory)

  assert.equal(config.serverUrl, '')
  assert.equal(config.window.width, DEFAULT_WIDTH)
  assert.equal(config.window.height, DEFAULT_HEIGHT)
  assert.equal(config.window.maximized, false)
})

test('server address and window state survive a round trip', (t) => {
  const directory = temporaryDirectory(t)
  saveConfig(directory, {
    serverUrl: 'http://127.0.0.1:8000/',
    window: { width: 1200, height: 800, maximized: true },
  })

  const config = loadConfig(directory)
  assert.equal(config.serverUrl, 'http://127.0.0.1:8000')
  assert.deepEqual(config.window, {
    width: 1200,
    height: 800,
    maximized: true,
  })
})

test('out-of-range window sizes are clamped', (t) => {
  const directory = temporaryDirectory(t)
  saveConfig(directory, {
    serverUrl: '',
    window: { width: 10, height: 100000, maximized: false },
  })

  const config = loadConfig(directory)
  assert.equal(config.window.width, MIN_WIDTH)
  assert.equal(config.window.height, 2160)
  assert.equal(config.window.height > MIN_HEIGHT, true)
})

test('unknown fields, including passwords, are never written', (t) => {
  const directory = temporaryDirectory(t)
  saveConfig(directory, {
    serverUrl: 'http://127.0.0.1:8000',
    window: { width: 1100, height: 700, maximized: false },
    password: 'must-not-be-saved',
    masterPassword: 'must-not-be-saved',
  })

  const raw = fs.readFileSync(path.join(directory, 'config.json'), 'utf8')
  assert.equal(raw.includes('password'), false)
  assert.equal(raw.includes('must-not-be-saved'), false)
})

test('a corrupt config is backed up and replaced with defaults', (t) => {
  const directory = temporaryDirectory(t)
  fs.writeFileSync(path.join(directory, 'config.json'), '{not json', 'utf8')

  const config = loadConfig(directory)
  assert.equal(config.serverUrl, '')

  const backups = fs
    .readdirSync(directory)
    .filter((name) => name.startsWith('config.corrupt-'))
  assert.equal(backups.length, 1)
})

test('saving window state keeps the configured server address', (t) => {
  const directory = temporaryDirectory(t)
  saveConfig(directory, {
    serverUrl: 'http://127.0.0.1:8000',
    window: { width: 1200, height: 800, maximized: false },
  })

  saveWindowState(
    directory,
    '',
    { width: 1000, height: 700 },
    true,
  )

  const config = loadConfig(directory)
  assert.equal(config.serverUrl, 'http://127.0.0.1:8000')
  assert.equal(config.window.maximized, true)
  assert.equal(config.window.width, 1000)
})

test('an invalid stored address is ignored instead of crashing', (t) => {
  const directory = temporaryDirectory(t)
  fs.writeFileSync(
    path.join(directory, 'config.json'),
    JSON.stringify({ serverUrl: 'file:///C:/', window: {} }),
    'utf8',
  )

  const config = loadConfig(directory)
  assert.equal(config.serverUrl, '')
})
