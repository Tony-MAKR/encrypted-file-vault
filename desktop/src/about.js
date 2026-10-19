'use strict'

const versionLabel = document.getElementById('version')
const buildTimeLabel = document.getElementById('build-time')
const serverUrlLabel = document.getElementById('server-url')
const settingsButton = document.getElementById('settings-button')
const closeButton = document.getElementById('close-button')

async function loadState() {
  if (!window.desktop) {
    serverUrlLabel.textContent = '客户端初始化失败'
    return
  }
  try {
    const state = await window.desktop.getState()
    versionLabel.textContent = state.version || '未知'
    buildTimeLabel.textContent = state.buildTime || '未知'
    serverUrlLabel.textContent = state.serverUrl || '尚未设置'
  } catch {
    serverUrlLabel.textContent = '读取失败'
  }
}

settingsButton.addEventListener('click', () => {
  if (window.desktop) {
    void window.desktop.openSettings()
  }
})

closeButton.addEventListener('click', () => {
  if (window.desktop) {
    void window.desktop.closeWindow()
  }
})

void loadState()
