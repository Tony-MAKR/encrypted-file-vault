'use strict'

/**
 * Connection test used by the settings page. It calls the public health
 * endpoint only, never sends credentials and follows no redirects.
 */

const { normalizeServerUrl } = require('./urls')

function describeFetchError(error) {
  if (error && error.name === 'AbortError') {
    return '连接超时。请确认服务器已启动，地址和端口正确。'
  }
  const code = String(
    (error && error.cause && error.cause.code) || (error && error.code) || '',
  )
  const messages = {
    ECONNREFUSED: '服务器拒绝连接。请确认服务器已启动，地址和端口正确。',
    ENOTFOUND: '找不到这个服务器地址，请检查拼写。',
    ETIMEDOUT: '连接服务器超时，请检查地址和网络。',
    UND_ERR_CONNECT_TIMEOUT: '连接服务器超时，请检查地址和网络。',
    EAI_AGAIN: '暂时无法解析服务器地址，请稍后重试。',
  }
  return messages[code] || '无法连接到服务器。请确认服务器已启动，并检查地址。'
}

async function testServer(rawUrl, options = {}) {
  const fetchImpl = options.fetchImpl || fetch
  const timeoutMs = options.timeoutMs || 6000

  let base
  try {
    base = normalizeServerUrl(rawUrl)
  } catch (error) {
    return { ok: false, error: error.message }
  }

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetchImpl(`${base}/api/v1/health/`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      redirect: 'error',
      signal: controller.signal,
    })
    if (!response.ok) {
      return {
        ok: false,
        error: `服务器返回 HTTP ${response.status}，请检查地址是否正确。`,
      }
    }
    const data = await response.json().catch(() => null)
    if (!data || data.status !== 'ok') {
      return {
        ok: false,
        error: '服务器响应异常，数据库可能不可用。请查看服务器窗口。',
      }
    }
    return {
      ok: true,
      serverUrl: base,
      version: String(data.version || '未知'),
    }
  } catch (error) {
    return { ok: false, error: describeFetchError(error) }
  } finally {
    clearTimeout(timeout)
  }
}

module.exports = { describeFetchError, testServer }
