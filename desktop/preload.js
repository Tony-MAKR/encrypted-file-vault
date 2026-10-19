'use strict'

/**
 * Minimal bridge between the desktop windows and the main process.
 *
 * The renderer never receives ipcRenderer, Node APIs, the file system or the
 * shell. Each exposed function maps to one narrowly scoped IPC handler that
 * validates the sender and its arguments in main.js.
 */

const { contextBridge, ipcRenderer } = require('electron')

function asText(value) {
  return typeof value === 'string' ? value.slice(0, 2048) : ''
}

const desktopApi = Object.freeze({
  getState: () => ipcRenderer.invoke('desktop:get-state'),
  testServer: (url) => ipcRenderer.invoke('desktop:test-server', asText(url)),
  saveServer: (url) => ipcRenderer.invoke('desktop:save-server', asText(url)),
  retry: () => ipcRenderer.invoke('desktop:retry'),
  openSettings: () => ipcRenderer.invoke('desktop:open-settings'),
  closeWindow: () => ipcRenderer.invoke('desktop:close-window'),
})

contextBridge.exposeInMainWorld('desktop', desktopApi)
