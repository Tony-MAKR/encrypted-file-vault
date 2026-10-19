'use strict'

/**
 * Server address validation shared by the main process, the settings page and
 * the unit tests. No Electron or network code lives here.
 */

const DEFAULT_SERVER_URL = 'http://127.0.0.1:8000'
const MAX_URL_LENGTH = 2048
const ALLOWED_PROTOCOLS = new Set(['http:', 'https:'])

class InvalidServerUrlError extends Error {
  constructor(message) {
    super(message)
    this.name = 'InvalidServerUrlError'
  }
}

function normalizeServerUrl(input) {
  if (typeof input !== 'string') {
    throw new InvalidServerUrlError('请输入服务器地址。')
  }
  const trimmed = input.trim()
  if (!trimmed) {
    throw new InvalidServerUrlError('请输入服务器地址。')
  }
  if (trimmed.length > MAX_URL_LENGTH) {
    throw new InvalidServerUrlError('服务器地址太长，请检查后重试。')
  }

  let parsed
  try {
    parsed = new URL(trimmed)
  } catch {
    throw new InvalidServerUrlError(
      '服务器地址格式不正确，请包含 http:// 或 https://。',
    )
  }

  if (!ALLOWED_PROTOCOLS.has(parsed.protocol)) {
    throw new InvalidServerUrlError(
      '只支持 http:// 或 https:// 开头的服务器地址。',
    )
  }
  if (parsed.username || parsed.password) {
    throw new InvalidServerUrlError('服务器地址不能包含用户名或密码。')
  }
  if (parsed.search) {
    throw new InvalidServerUrlError('服务器地址不能包含 ? 查询参数。')
  }
  if (parsed.hash) {
    throw new InvalidServerUrlError('服务器地址不能包含 # 片段。')
  }

  const pathname = parsed.pathname.replace(/\/+$/, '')
  return `${parsed.protocol}//${parsed.host}${pathname}`
}

function originOf(serverUrl) {
  try {
    return new URL(serverUrl).origin
  } catch {
    return null
  }
}

function isSameOrigin(targetUrl, allowedOrigin) {
  if (!allowedOrigin) {
    return false
  }
  try {
    return new URL(targetUrl).origin === allowedOrigin
  } catch {
    return false
  }
}

function isSafeExternalUrl(targetUrl) {
  try {
    const parsed = new URL(targetUrl)
    return (
      ALLOWED_PROTOCOLS.has(parsed.protocol) &&
      !parsed.username &&
      !parsed.password
    )
  } catch {
    return false
  }
}

module.exports = {
  DEFAULT_SERVER_URL,
  InvalidServerUrlError,
  MAX_URL_LENGTH,
  isSafeExternalUrl,
  isSameOrigin,
  normalizeServerUrl,
  originOf,
}
