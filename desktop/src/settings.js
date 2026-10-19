'use strict'

const form = document.getElementById('settings-form')
const input = document.getElementById('server-url')
const statusBox = document.getElementById('status')
const testButton = document.getElementById('test-button')
const saveButton = document.getElementById('save-button')
const cancelButton = document.getElementById('cancel-button')
const firstRunHelp = document.getElementById('first-run-help')
const versionLabel = document.getElementById('version')

let busy = false

function showStatus(kind, message) {
  statusBox.hidden = false
  statusBox.className = `status status-${kind}`
  statusBox.textContent = message
}

function hideStatus() {
  statusBox.hidden = true
  statusBox.textContent = ''
}

function setBusy(value) {
  busy = value
  testButton.disabled = value
  saveButton.disabled = value
  input.disabled = value
}

function requireBridge() {
  if (!window.desktop) {
    showStatus('error', '客户端初始化失败，请关闭后重新打开。')
    setBusy(true)
    return false
  }
  return true
}

async function loadState() {
  if (!requireBridge()) {
    return
  }
  try {
    const state = await window.desktop.getState()
    input.value = state.serverUrl || state.defaultServerUrl
    versionLabel.textContent = state.version || '未知'

    const firstRun =
      new URLSearchParams(window.location.search).get('firstRun') === '1'
    firstRunHelp.hidden = !firstRun
    cancelButton.hidden = firstRun
    if (firstRun) {
      input.focus()
      input.select()
    }
  } catch {
    showStatus('error', '读取客户端设置失败，请关闭后重新打开。')
  }
}

async function testConnection() {
  if (busy || !requireBridge()) {
    return
  }
  setBusy(true)
  showStatus('info', '正在连接服务器…')
  try {
    const result = await window.desktop.testServer(input.value)
    if (result.ok) {
      input.value = result.serverUrl
      showStatus(
        'success',
        `连接成功。服务器版本 ${result.version}。可以点“保存并连接”。`,
      )
    } else {
      showStatus('error', result.error || '连接失败，请检查地址。')
    }
  } catch {
    showStatus('error', '连接测试失败，请稍后重试。')
  } finally {
    setBusy(false)
  }
}

async function saveAndConnect(event) {
  event.preventDefault()
  if (busy || !requireBridge()) {
    return
  }
  if (!input.value.trim()) {
    showStatus('error', '请输入服务器地址。')
    input.focus()
    return
  }

  setBusy(true)
  showStatus('info', '正在保存并连接…')
  try {
    const result = await window.desktop.saveServer(input.value)
    if (!result.ok) {
      showStatus('error', result.error || '保存失败，请检查地址。')
      setBusy(false)
    }
    // On success the main process closes this window and opens the server.
  } catch {
    showStatus('error', '保存失败，请稍后重试。')
    setBusy(false)
  }
}

testButton.addEventListener('click', () => void testConnection())
form.addEventListener('submit', (event) => void saveAndConnect(event))
cancelButton.addEventListener('click', () => {
  if (window.desktop) {
    void window.desktop.closeWindow()
  }
})
input.addEventListener('input', () => {
  if (!statusBox.hidden && statusBox.classList.contains('status-error')) {
    hideStatus()
  }
})

void loadState()
