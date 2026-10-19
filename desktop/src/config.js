'use strict'

/**
 * Client-side configuration. Only the server address and window geometry are
 * stored. Passwords, master passwords, session contents and vault material are
 * never written here.
 */

const fs = require('node:fs')
const path = require('node:path')

const { normalizeServerUrl } = require('./urls')

const CONFIG_FILENAME = 'config.json'
const CONFIG_VERSION = 1
const MIN_WIDTH = 960
const MIN_HEIGHT = 640
const DEFAULT_WIDTH = 1280
const DEFAULT_HEIGHT = 860

function clampInteger(value, minimum, maximum, fallback) {
  if (!Number.isInteger(value)) {
    return fallback
  }
  return Math.min(Math.max(value, minimum), maximum)
}

function sanitizeWindow(raw) {
  const source = raw && typeof raw === 'object' ? raw : {}
  return {
    width: clampInteger(source.width, MIN_WIDTH, 4096, DEFAULT_WIDTH),
    height: clampInteger(source.height, MIN_HEIGHT, 2160, DEFAULT_HEIGHT),
    maximized: source.maximized === true,
  }
}

function defaultConfig() {
  return {
    version: CONFIG_VERSION,
    serverUrl: '',
    window: sanitizeWindow(null),
  }
}

function configPath(userDataDir) {
  return path.join(userDataDir, CONFIG_FILENAME)
}

function backupCorruptConfig(userDataDir) {
  const source = configPath(userDataDir)
  if (!fs.existsSync(source)) {
    return
  }
  const stamp = new Date().toISOString().replace(/[:.]/g, '-')
  const target = path.join(userDataDir, `config.corrupt-${stamp}.json`)
  try {
    fs.renameSync(source, target)
  } catch {
    // If the backup fails, keep the original file untouched. The next save
    // will replace it, which is acceptable for non-secret client settings.
  }
}

function loadConfig(userDataDir) {
  const file = configPath(userDataDir)
  let parsed
  try {
    parsed = JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch (error) {
    if (error && error.code !== 'ENOENT') {
      backupCorruptConfig(userDataDir)
    }
    return defaultConfig()
  }

  if (!parsed || typeof parsed !== 'object') {
    backupCorruptConfig(userDataDir)
    return defaultConfig()
  }

  let serverUrl = ''
  if (typeof parsed.serverUrl === 'string' && parsed.serverUrl) {
    try {
      serverUrl = normalizeServerUrl(parsed.serverUrl)
    } catch {
      serverUrl = ''
    }
  }

  return {
    version: CONFIG_VERSION,
    serverUrl,
    window: sanitizeWindow(parsed.window),
  }
}

function saveConfig(userDataDir, config) {
  const normalized = {
    version: CONFIG_VERSION,
    serverUrl: config && config.serverUrl ? normalizeServerUrl(config.serverUrl) : '',
    window: sanitizeWindow(config && config.window),
  }

  fs.mkdirSync(userDataDir, { recursive: true })
  const target = configPath(userDataDir)
  const temporary = `${target}.tmp`
  fs.writeFileSync(temporary, `${JSON.stringify(normalized, null, 2)}\n`, {
    encoding: 'utf8',
    mode: 0o600,
  })
  fs.renameSync(temporary, target)
  return normalized
}

function saveWindowState(userDataDir, serverUrl, bounds, maximized) {
  const config = loadConfig(userDataDir)
  config.serverUrl = serverUrl || config.serverUrl
  config.window = sanitizeWindow({
    width: bounds && bounds.width,
    height: bounds && bounds.height,
    maximized,
  })
  return saveConfig(userDataDir, config)
}

module.exports = {
  CONFIG_FILENAME,
  CONFIG_VERSION,
  DEFAULT_HEIGHT,
  DEFAULT_WIDTH,
  MIN_HEIGHT,
  MIN_WIDTH,
  configPath,
  defaultConfig,
  loadConfig,
  saveConfig,
  saveWindowState,
  sanitizeWindow,
}
