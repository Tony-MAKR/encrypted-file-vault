'use strict'

const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { pathToFileURL } = require('node:url')

const {
  app,
  BrowserWindow,
  Menu,
  dialog,
  ipcMain,
  session,
  shell,
} = require('electron')

const {
  DEFAULT_SERVER_URL,
  isSafeExternalUrl,
  isSameOrigin,
  normalizeServerUrl,
  originOf,
} = require('./src/urls')
const { loadConfig, saveConfig, saveWindowState } = require('./src/config')
const { testServer } = require('./src/server-check')

const APP_TITLE = '加密文件管理系统'
const IS_PACKAGED = app.isPackaged
const IS_SMOKE_TEST = process.argv.includes('--smoke-test')
const LOCAL_PAGES_DIR = path.join(__dirname, 'src')
const LOCAL_PAGES_URL = `${pathToFileURL(LOCAL_PAGES_DIR).href}/`

// Keep the smoke test away from the real client configuration and session.
if (IS_SMOKE_TEST) {
  app.setPath(
    'userData',
    path.join(os.tmpdir(), `encrypted-file-desktop-smoke-${process.pid}`),
  )
}

app.enableSandbox()

let mainWindow = null
let settingsWindow = null
let aboutWindow = null
let allowedOrigin = null
let mainWindowState = 'server'
let lastConnectionError = ''
let loadSequence = 0
let quitting = false

function localPage(name) {
  return path.join(LOCAL_PAGES_DIR, name)
}

function isLocalPageUrl(targetUrl) {
  return typeof targetUrl === 'string' && targetUrl.startsWith(LOCAL_PAGES_URL)
}

function readBuildInfo() {
  const files = []
  if (IS_PACKAGED) {
    files.push(path.join(process.resourcesPath, 'build-info.json'))
  }
  files.push(path.join(__dirname, 'dist-build-info.json'))

  for (const file of files) {
    try {
      const parsed = JSON.parse(fs.readFileSync(file, 'utf8'))
      return {
        version: app.getVersion(),
        buildTime:
          typeof parsed.buildTime === 'string' && parsed.buildTime
            ? parsed.buildTime
            : '未知',
      }
    } catch {
      // Try the next location.
    }
  }
  return { version: app.getVersion(), buildTime: '开发模式' }
}

const buildInfo = readBuildInfo()

function baseWebPreferences() {
  return {
    preload: path.join(__dirname, 'preload.js'),
    nodeIntegration: false,
    nodeIntegrationInWorker: false,
    nodeIntegrationInSubFrames: false,
    contextIsolation: true,
    sandbox: true,
    webSecurity: true,
    allowRunningInsecureContent: false,
    webviewTag: false,
    navigateOnDragDrop: false,
    safeDialogs: true,
    spellcheck: false,
    devTools: !IS_PACKAGED && !IS_SMOKE_TEST,
  }
}

function openExternal(targetUrl) {
  if (!isSafeExternalUrl(targetUrl)) {
    return
  }
  shell.openExternal(targetUrl).catch(() => {
    // Opening the system browser is best-effort; never fall back to in-app
    // navigation for an untrusted address.
  })
}

function attachMainWindowGuards(win) {
  win.webContents.setWindowOpenHandler(({ url }) => {
    openExternal(url)
    return { action: 'deny' }
  })

  const guard = (event, targetUrl) => {
    if (isLocalPageUrl(targetUrl)) {
      return
    }
    if (mainWindowState === 'server' && isSameOrigin(targetUrl, allowedOrigin)) {
      return
    }
    event.preventDefault()
    if (mainWindowState === 'server') {
      openExternal(targetUrl)
    }
  }

  win.webContents.on('will-navigate', guard)
  // A redirect to another origin is blocked outright rather than opened in the
  // system browser: a server redirect should never be able to launch an
  // external page on its own.
  win.webContents.on('will-redirect', (event, targetUrl) => {
    if (isLocalPageUrl(targetUrl)) {
      return
    }
    if (mainWindowState === 'server' && isSameOrigin(targetUrl, allowedOrigin)) {
      return
    }
    event.preventDefault()
  })
}

function attachLocalWindowGuards(win) {
  win.webContents.on('will-navigate', (event) => {
    event.preventDefault()
  })
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
}

function showWindowWhenReady(win) {
  const timer = setTimeout(() => {
    if (!win.isDestroyed() && !win.isVisible()) {
      win.show()
    }
  }, 1500)
  win.once('ready-to-show', () => {
    clearTimeout(timer)
    if (!win.isDestroyed()) {
      win.show()
    }
  })
  win.once('closed', () => clearTimeout(timer))
}

function persistMainWindowState() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return
  }
  try {
    const current = loadConfig(app.getPath('userData'))
    const maximized = mainWindow.isMaximized()
    const bounds = maximized ? mainWindow.getNormalBounds() : mainWindow.getBounds()
    saveWindowState(
      app.getPath('userData'),
      current.serverUrl,
      bounds,
      maximized,
    )
  } catch {
    // Losing window geometry is harmless; never block shutdown.
  }
}

function describeLoadError(error) {
  const message = String((error && error.message) || '')
  const code =
    String((error && error.code) || '') ||
    (/ERR_[A-Z_]+/.exec(message) || [])[0] ||
    ''

  const messages = {
    ERR_CONNECTION_REFUSED:
      '服务器拒绝连接。请确认服务器已启动，且地址和端口正确。',
    ERR_CONNECTION_TIMED_OUT: '连接服务器超时。请检查地址和网络。',
    ERR_NAME_NOT_RESOLVED: '找不到这个服务器地址，请检查拼写。',
    ERR_INTERNET_DISCONNECTED: '电脑当前没有网络连接。',
    ERR_ADDRESS_UNREACHABLE: '无法访问这个服务器地址。',
    ERR_CONNECTION_RESET: '连接被服务器中断，请稍后重试。',
    ERR_CERT_AUTHORITY_INVALID:
      '服务器证书不受信任。当前阶段只应连接本机服务器。',
    ERR_CERT_COMMON_NAME_INVALID: '服务器证书与地址不匹配。',
    ERR_SSL_PROTOCOL_ERROR: '无法建立安全连接，请检查服务器地址。',
  }
  return messages[code] || '无法连接到服务器。请确认服务器已启动，并检查地址。'
}

async function loadServer(win, serverUrl) {
  if (!win || win.isDestroyed()) {
    return
  }

  const sequence = ++loadSequence
  let normalized
  try {
    normalized = normalizeServerUrl(serverUrl)
  } catch (error) {
    lastConnectionError = error.message
    mainWindowState = 'error'
    allowedOrigin = null
    try {
      await win.loadFile(localPage('error.html'))
    } catch {
      // The window is likely closing; nothing else to do.
    }
    return
  }

  allowedOrigin = originOf(normalized)
  mainWindowState = 'server'
  lastConnectionError = ''

  try {
    await win.loadURL(normalized)
    if (sequence === loadSequence) {
      lastConnectionError = ''
      mainWindowState = 'server'
    }
  } catch (error) {
    if (win.isDestroyed() || sequence !== loadSequence) {
      return
    }
    if (error && error.code === 'ERR_ABORTED') {
      return
    }
    lastConnectionError = describeLoadError(error)
    mainWindowState = 'error'
    allowedOrigin = null
    try {
      await win.loadFile(localPage('error.html'))
    } catch {
      // The window is likely closing; nothing else to do.
    }
  }
}

function createMainWindow(serverUrl) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.focus()
    return mainWindow
  }

  const config = loadConfig(app.getPath('userData'))
  const bounds = config.window

  mainWindow = new BrowserWindow({
    title: APP_TITLE,
    width: bounds.width,
    height: bounds.height,
    minWidth: 960,
    minHeight: 640,
    show: false,
    backgroundColor: '#f4f7f6',
    autoHideMenuBar: false,
    webPreferences: baseWebPreferences(),
  })

  const win = mainWindow
  attachMainWindowGuards(win)
  showWindowWhenReady(win)

  if (bounds.maximized) {
    win.maximize()
  }

  win.on('page-title-updated', (event) => {
    event.preventDefault()
    win.setTitle(APP_TITLE)
  })
  win.on('close', persistMainWindowState)
  win.on('closed', () => {
    if (mainWindow === win) {
      mainWindow = null
      allowedOrigin = null
    }
  })

  void loadServer(win, serverUrl)
  return win
}

function createSettingsWindow() {
  if (settingsWindow && !settingsWindow.isDestroyed()) {
    settingsWindow.focus()
    return settingsWindow
  }

  const firstRun = !mainWindow || mainWindow.isDestroyed()
  const parent =
    mainWindow && !mainWindow.isDestroyed() ? mainWindow : undefined

  settingsWindow = new BrowserWindow({
    title: `服务器设置 - ${APP_TITLE}`,
    width: 600,
    height: 610,
    minWidth: 520,
    minHeight: 520,
    parent,
    modal: false,
    minimizable: false,
    maximizable: false,
    show: false,
    backgroundColor: '#f4f7f6',
    autoHideMenuBar: true,
    webPreferences: baseWebPreferences(),
  })

  const win = settingsWindow
  attachLocalWindowGuards(win)
  showWindowWhenReady(win)
  win.on('closed', () => {
    if (settingsWindow === win) {
      settingsWindow = null
    }
    if (!mainWindow && !quitting) {
      app.quit()
    }
  })

  void win.loadFile(localPage('settings.html'), {
    query: { firstRun: firstRun ? '1' : '0' },
  })
  return win
}

function createAboutWindow() {
  if (aboutWindow && !aboutWindow.isDestroyed()) {
    aboutWindow.focus()
    return aboutWindow
  }

  aboutWindow = new BrowserWindow({
    title: `关于 - ${APP_TITLE}`,
    width: 540,
    height: 560,
    minWidth: 480,
    minHeight: 500,
    parent: mainWindow && !mainWindow.isDestroyed() ? mainWindow : undefined,
    modal: false,
    minimizable: false,
    maximizable: false,
    show: false,
    backgroundColor: '#f4f7f6',
    autoHideMenuBar: true,
    webPreferences: baseWebPreferences(),
  })

  const win = aboutWindow
  attachLocalWindowGuards(win)
  showWindowWhenReady(win)
  win.on('closed', () => {
    if (aboutWindow === win) {
      aboutWindow = null
    }
  })

  void win.loadFile(localPage('about.html'))
  return win
}

function buildMenu() {
  const focusedWindow = () => BrowserWindow.getFocusedWindow()

  const viewItems = [
    {
      label: '重新加载',
      accelerator: 'CmdOrCtrl+R',
      click: () => {
        const win = focusedWindow()
        if (win) {
          win.reload()
        }
      },
    },
    {
      label: '强制重新加载',
      accelerator: 'CmdOrCtrl+Shift+R',
      click: () => {
        const win = focusedWindow()
        if (win) {
          win.webContents.reloadIgnoringCache()
        }
      },
    },
    { type: 'separator' },
    { label: '放大', role: 'zoomIn' },
    { label: '缩小', role: 'zoomOut' },
    { label: '实际大小', role: 'resetZoom' },
  ]
  if (IS_PACKAGED === false && IS_SMOKE_TEST === false) {
    viewItems.push(
      { type: 'separator' },
      { label: '开发者工具', role: 'toggleDevTools' },
    )
  }

  const template = [
    {
      label: '文件',
      submenu: [
        {
          label: '服务器设置…',
          accelerator: 'CmdOrCtrl+,',
          click: () => createSettingsWindow(),
        },
        { type: 'separator' },
        { label: '退出', role: 'quit' },
      ],
    },
    {
      label: '视图',
      submenu: viewItems,
    },
    {
      label: '帮助',
      submenu: [
        {
          label: '关于加密文件管理系统',
          click: () => createAboutWindow(),
        },
      ],
    },
  ]

  Menu.setApplicationMenu(Menu.buildFromTemplate(template))
}

function configureSessionSecurity() {
  const defaultSession = session.defaultSession

  // Clipboard writing is required for "复制密码"; everything else (camera,
  // microphone, geolocation, notifications, …) is denied.
  const isAllowedPermission = (permission) =>
    permission === 'clipboard-sanitized-write'
  defaultSession.setPermissionRequestHandler(
    (_webContents, permission, callback) => {
      callback(isAllowedPermission(permission))
    },
  )
  defaultSession.setPermissionCheckHandler(
    (_webContents, permission) => isAllowedPermission(permission),
  )

  defaultSession.on('will-download', (_event, item) => {
    const suggested = path.basename(item.getFilename() || 'download')
    item.pause()
    dialog
      .showSaveDialog({
        title: '保存文件',
        defaultPath: path.join(app.getPath('downloads'), suggested),
        buttonLabel: '保存',
        properties: ['showOverwriteConfirmation'],
      })
      .then((result) => {
        if (result.canceled || !result.filePath) {
          item.cancel()
          return
        }
        item.setSavePath(result.filePath)
        item.resume()
      })
      .catch(() => item.cancel())
  })
}

function senderWindow(event) {
  return BrowserWindow.fromWebContents(event.sender)
}

function isOurWindow(event) {
  const win = senderWindow(event)
  return Boolean(
    win && (win === mainWindow || win === settingsWindow || win === aboutWindow),
  )
}

function isSender(event, win) {
  return Boolean(win && !win.isDestroyed() && event.sender === win.webContents)
}

function pageFor(win) {
  if (win === settingsWindow) {
    return 'settings'
  }
  if (win === aboutWindow) {
    return 'about'
  }
  return mainWindowState === 'error' ? 'error' : 'main'
}

function currentState(event) {
  const win = senderWindow(event)
  const config = loadConfig(app.getPath('userData'))
  return {
    page: pageFor(win),
    appTitle: APP_TITLE,
    serverUrl: config.serverUrl,
    defaultServerUrl: DEFAULT_SERVER_URL,
    error: lastConnectionError,
    version: buildInfo.version,
    buildTime: buildInfo.buildTime,
  }
}

function registerIpcHandlers() {
  ipcMain.handle('desktop:get-state', (event) => {
    if (!isOurWindow(event)) {
      return { page: 'unknown', error: '不允许的操作。' }
    }
    return currentState(event)
  })

  ipcMain.handle('desktop:test-server', async (event, rawUrl) => {
    if (!isSender(event, settingsWindow)) {
      return { ok: false, error: '不允许的操作。' }
    }
    return testServer(rawUrl)
  })

  ipcMain.handle('desktop:save-server', async (event, rawUrl) => {
    if (!isSender(event, settingsWindow)) {
      return { ok: false, error: '不允许的操作。' }
    }

    let normalized
    try {
      normalized = normalizeServerUrl(rawUrl)
    } catch (error) {
      return { ok: false, error: error.message }
    }

    try {
      const config = loadConfig(app.getPath('userData'))
      config.serverUrl = normalized
      saveConfig(app.getPath('userData'), config)
    } catch {
      return { ok: false, error: '无法保存服务器地址，请检查磁盘权限。' }
    }

    if (mainWindow && !mainWindow.isDestroyed()) {
      void loadServer(mainWindow, normalized)
    } else {
      createMainWindow(normalized)
    }

    if (settingsWindow && !settingsWindow.isDestroyed()) {
      settingsWindow.close()
    }
    return { ok: true, serverUrl: normalized }
  })

  ipcMain.handle('desktop:retry', async (event) => {
    if (!isSender(event, mainWindow)) {
      return { ok: false, error: '不允许的操作。' }
    }
    const config = loadConfig(app.getPath('userData'))
    if (!config.serverUrl) {
      createSettingsWindow()
      return { ok: false, error: '请先设置服务器地址。' }
    }
    void loadServer(mainWindow, config.serverUrl)
    return { ok: true }
  })

  ipcMain.handle('desktop:open-settings', (event) => {
    if (!isOurWindow(event)) {
      return { ok: false, error: '不允许的操作。' }
    }
    createSettingsWindow()
    return { ok: true }
  })

  ipcMain.handle('desktop:close-window', (event) => {
    if (!isOurWindow(event)) {
      return { ok: false, error: '不允许的操作。' }
    }
    const win = senderWindow(event)
    if (win && !win.isDestroyed()) {
      win.close()
    }
    return { ok: true }
  })
}

function startApp() {
  configureSessionSecurity()
  buildMenu()
  registerIpcHandlers()

  if (IS_SMOKE_TEST) {
    const smokeServerArg = process.argv.find((arg) =>
      arg.startsWith('--smoke-server='),
    )
    if (smokeServerArg) {
      // Test-only: load a real server in the main window and verify that the
      // React login page rendered. Uses the temporary smoke userData dir.
      let smokeServer
      try {
        smokeServer = normalizeServerUrl(
          smokeServerArg.slice('--smoke-server='.length),
        )
        const config = loadConfig(app.getPath('userData'))
        config.serverUrl = smokeServer
        saveConfig(app.getPath('userData'), config)
      } catch {
        console.error('SMOKE_MAIN_FAILED')
        app.exit(1)
        return
      }

      const expectError = process.argv.includes('--smoke-expect-error')
      const successExpression = expectError
        ? "location.protocol === 'file:' && Boolean(document.querySelector('#retry-button'))"
        : "location.protocol.startsWith('http') && Boolean(document.querySelector('#username'))"

      const win = createMainWindow(smokeServer)
      const deadline = Date.now() + 20000
      const timer = setTimeout(() => {
        console.error('SMOKE_MAIN_TIMEOUT')
        app.exit(1)
      }, 20000)

      const poll = () => {
        if (win.isDestroyed()) {
          clearTimeout(timer)
          app.exit(1)
          return
        }
        win.webContents
          .executeJavaScript(successExpression)
          .then((ok) => {
            if (ok) {
              clearTimeout(timer)
              console.log(expectError ? 'SMOKE_ERROR_PAGE_OK' : 'SMOKE_MAIN_OK')
              app.exit(0)
            } else if (Date.now() > deadline) {
              clearTimeout(timer)
              console.error('SMOKE_MAIN_FAILED')
              app.exit(1)
            } else {
              setTimeout(poll, 250)
            }
          })
          .catch(() => {
            if (Date.now() > deadline) {
              clearTimeout(timer)
              console.error('SMOKE_MAIN_FAILED')
              app.exit(1)
            } else {
              setTimeout(poll, 250)
            }
          })
      }
      win.webContents.once('did-finish-load', () => setTimeout(poll, 250))
      return
    }

    const win = createSettingsWindow()
    const deadline = Date.now() + 15000
    const timer = setTimeout(() => {
      console.error('SMOKE_TIMEOUT')
      app.exit(1)
    }, 15000)

    const poll = () => {
      if (win.isDestroyed()) {
        clearTimeout(timer)
        app.exit(1)
        return
      }
      win.webContents
        .executeJavaScript(
          "Boolean(window.desktop && document.querySelector('#settings-form') && document.getElementById('version') && document.getElementById('version').textContent !== '—')",
        )
        .then((ok) => {
          if (ok) {
            clearTimeout(timer)
            console.log('SMOKE_OK')
            app.exit(0)
          } else if (Date.now() > deadline) {
            clearTimeout(timer)
            console.error('SMOKE_FAILED')
            app.exit(1)
          } else {
            setTimeout(poll, 200)
          }
        })
        .catch(() => {
          if (Date.now() > deadline) {
            clearTimeout(timer)
            console.error('SMOKE_FAILED')
            app.exit(1)
          } else {
            setTimeout(poll, 200)
          }
        })
    }
    win.webContents.once('did-finish-load', () => setTimeout(poll, 200))
    return
  }

  const config = loadConfig(app.getPath('userData'))
  if (config.serverUrl) {
    createMainWindow(config.serverUrl)
  } else {
    createSettingsWindow()
  }
}

const hasSingleInstanceLock = app.requestSingleInstanceLock()
if (!hasSingleInstanceLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    const win =
      mainWindow && !mainWindow.isDestroyed()
        ? mainWindow
        : settingsWindow && !settingsWindow.isDestroyed()
          ? settingsWindow
          : null
    if (win) {
      if (win.isMinimized()) {
        win.restore()
      }
      win.focus()
    }
  })

  app.on('web-contents-created', (_event, contents) => {
    contents.on('will-attach-webview', (event) => {
      event.preventDefault()
    })
  })

  app.on('before-quit', () => {
    quitting = true
  })

  app.on('window-all-closed', () => {
    app.quit()
  })

  app.whenReady().then(startApp)
}
