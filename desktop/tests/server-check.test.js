'use strict'

const test = require('node:test')
const assert = require('node:assert/strict')
const http = require('node:http')

const { describeFetchError, testServer } = require('../src/server-check')

function startServer(t, handler) {
  const server = http.createServer(handler)
  return new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      t.after(
        () =>
          new Promise((done) => {
            server.close(() => done())
          }),
      )
      resolve(`http://127.0.0.1:${server.address().port}`)
    })
  })
}

function json(response, status, payload) {
  response.writeHead(status, { 'Content-Type': 'application/json' })
  response.end(JSON.stringify(payload))
}

test('a healthy server returns its version', async (t) => {
  const base = await startServer(t, (request, response) => {
    assert.equal(request.url, '/api/v1/health/')
    json(response, 200, {
      status: 'ok',
      database: 'ok',
      version: '1.0.0',
    })
  })

  const result = await testServer(`${base}/`)
  assert.equal(result.ok, true)
  assert.equal(result.serverUrl, base)
  assert.equal(result.version, '1.0.0')
})

test('an HTTP error is reported without leaking details', async (t) => {
  const base = await startServer(t, (_request, response) => {
    json(response, 500, { detail: 'secret internal error' })
  })

  const result = await testServer(base)
  assert.equal(result.ok, false)
  assert.match(result.error, /HTTP 500/)
  assert.equal(result.error.includes('secret internal error'), false)
})

test('a degraded database is reported as a failure', async (t) => {
  const base = await startServer(t, (_request, response) => {
    json(response, 503, { status: 'degraded', database: 'error' })
  })

  const result = await testServer(base)
  assert.equal(result.ok, false)
  assert.match(result.error, /HTTP 503/)
})

test('an invalid address is rejected before any request', async () => {
  const result = await testServer('file:///C:/Windows')
  assert.equal(result.ok, false)
  assert.match(result.error, /http/)
})

test('an unreachable address produces a friendly error', async () => {
  const result = await testServer('http://127.0.0.1:9', { timeoutMs: 1500 })
  assert.equal(result.ok, false)
  assert.ok(result.error.length > 0)
  assert.equal(result.error.includes('ECONNREFUSED'), false)
})

test('a timeout is reported in plain language', async () => {
  const abortError = new Error('aborted')
  abortError.name = 'AbortError'

  const result = await testServer('http://127.0.0.1:8000', {
    fetchImpl: async () => {
      throw abortError
    },
  })
  assert.equal(result.ok, false)
  assert.match(result.error, /超时/)
})

test('network error codes map to readable messages', () => {
  const refused = new Error('connect failed')
  refused.cause = { code: 'ECONNREFUSED' }
  assert.match(describeFetchError(refused), /拒绝连接/)

  const unknown = new Error('other')
  assert.match(describeFetchError(unknown), /无法连接/)
})
