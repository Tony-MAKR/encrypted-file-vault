'use strict'

const test = require('node:test')
const assert = require('node:assert/strict')

const {
  DEFAULT_SERVER_URL,
  InvalidServerUrlError,
  isSafeExternalUrl,
  isSameOrigin,
  normalizeServerUrl,
  originOf,
} = require('../src/urls')

test('the default server address is accepted unchanged', () => {
  assert.equal(normalizeServerUrl(DEFAULT_SERVER_URL), DEFAULT_SERVER_URL)
})

test('addresses are trimmed and trailing slashes are removed', () => {
  assert.equal(
    normalizeServerUrl('  http://127.0.0.1:8000/  '),
    'http://127.0.0.1:8000',
  )
  assert.equal(
    normalizeServerUrl('https://vault.example.test/app/'),
    'https://vault.example.test/app',
  )
})

test('the scheme is normalized to lower case', () => {
  assert.equal(
    normalizeServerUrl('HTTP://127.0.0.1:8000'),
    'http://127.0.0.1:8000',
  )
})

for (const value of [
  '',
  '   ',
  '127.0.0.1:8000',
  'file:///C:/Windows',
  'javascript:alert(1)',
  'data:text/html,hello',
  'ftp://127.0.0.1',
  'http://user:secret@127.0.0.1:8000',
  'http://127.0.0.1:8000/?token=x',
  'http://127.0.0.1:8000/#section',
]) {
  test(`invalid address is rejected: ${JSON.stringify(value)}`, () => {
    assert.throws(() => normalizeServerUrl(value), InvalidServerUrlError)
  })
}

test('non-string and oversized addresses are rejected', () => {
  assert.throws(() => normalizeServerUrl(null), InvalidServerUrlError)
  assert.throws(
    () => normalizeServerUrl(`http://127.0.0.1/${'a'.repeat(3000)}`),
    InvalidServerUrlError,
  )
})

test('origins are compared exactly', () => {
  const origin = originOf('http://127.0.0.1:8000/app')
  assert.equal(origin, 'http://127.0.0.1:8000')
  assert.equal(isSameOrigin('http://127.0.0.1:8000/admin/items', origin), true)
  assert.equal(isSameOrigin('http://127.0.0.1:5173/', origin), false)
  assert.equal(isSameOrigin('https://127.0.0.1:8000/', origin), false)
  assert.equal(isSameOrigin('file:///C:/secret.txt', origin), false)
  assert.equal(isSameOrigin('not a url', origin), false)
})

test('external links must be http(s) without credentials', () => {
  assert.equal(isSafeExternalUrl('https://example.com/help'), true)
  assert.equal(isSafeExternalUrl('http://127.0.0.1:8000/'), true)
  assert.equal(isSafeExternalUrl('file:///C:/Windows/System32'), false)
  assert.equal(isSafeExternalUrl('javascript:alert(1)'), false)
  assert.equal(isSafeExternalUrl('https://user:pass@example.com/'), false)
})
