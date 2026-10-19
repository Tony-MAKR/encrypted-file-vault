'use strict'

const errorMessage = document.getElementById('error-message')
const serverUrlLabel = document.getElementById('server-url')
const versionLabel = document.getElementById('version')
const retryButton = document.getElementById('retry-button')
const settingsButton = document.getElementById('settings-button')

let busy = false

async function loadState() {
  if (!window.desktop) {
    errorMessage.textContent = '客户端初始化失败，请关闭后重新打开。'
    retryButton.disabled = true
    settingsButton.disabled = true
    return
  }
  try {
    const state = await window.desktop.getState()
    errorMessage.textContent =
      state.error || '无法连接到服务器。请确认服务器已启动。'
    serverUrlLabel.textContent = state.serverUrl || '尚未设置'
    versionLabel.textContent = state.version || '未知'
  } catch {
    errorMessage.textContent = '读取连接信息失败，请点“重试连接”。'
  }
}

async function retry() {
  if (busy || !window.desktop) {
    return
  }
  busy = true
  retryButton.disabled = true
  settingsButton.disabled = true
  errorMessage.textContent = '正在重新连接…'
  try {
    const result = await window.desktop.retry()
    if (!result.ok) {
      errorMessage.textContent = result.error || '无法重试，请修改服务器地址。'
      busy = false
      retryButton.disabled = false
      settingsButton.disabled = false
    }
  } catch {
    errorMessage.textContent = '重试失败，请修改服务器地址或稍后再试。'
    busy = false
    retryButton.disabled = false
    settingsButton.disabled = false
  }
}

retryButton.addEventListener('click', () => void retry())
settingsButton.addEventListener('click', () => {
  if (window.desktop) {
    void window.desktop.openSettings()
  }
})

void loadState()
