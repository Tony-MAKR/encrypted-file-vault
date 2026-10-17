import { useCallback, useEffect, useState } from 'react'
import './App.css'

type HealthPayload = {
  status: string
  database: string
  version: string
}

type HealthState =
  | { kind: 'loading' }
  | { kind: 'ok'; data: HealthPayload }
  | { kind: 'error'; message: string }

const apiBaseUrl = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'
).replace(/\/$/, '')
const healthUrl = `${apiBaseUrl}/api/v1/health/`

function App() {
  const [health, setHealth] = useState<HealthState>({ kind: 'loading' })
  const [lastChecked, setLastChecked] = useState<string>('')

  const checkHealth = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await fetch(healthUrl, {
        headers: { Accept: 'application/json' },
        signal,
      })
      const data = (await response.json()) as HealthPayload

      if (!response.ok || data.status !== 'ok') {
        setHealth({
          kind: 'error',
          message: `后端返回异常状态（HTTP ${response.status}）。请查看后端日志。`,
        })
      } else {
        setHealth({ kind: 'ok', data })
      }
      setLastChecked(new Date().toLocaleTimeString('zh-CN'))
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return
      }
      setHealth({
        kind: 'error',
        message: '无法连接后端。请确认后端已启动，并检查地址是否正确。',
      })
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    // The state update happens after the async request resolves, not during
    // the effect body; this lint rule cannot see through the promise.
    // oxlint-disable-next-line react/set-state-in-effect
    void checkHealth(controller.signal)
    return () => controller.abort()
  }, [checkHealth])

  const refreshHealth = () => {
    setHealth({ kind: 'loading' })
    void checkHealth()
  }

  const isLoading = health.kind === 'loading'
  const statusLabel =
    health.kind === 'loading'
      ? '正在检查后端…'
      : health.kind === 'ok'
        ? '后端连接正常'
        : '后端连接异常'

  return (
    <div className="app-shell">
      <header className="hero">
        <div className="hero-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" role="presentation">
            <path d="M7 10V7a5 5 0 0 1 10 0v3" />
            <rect x="4" y="10" width="16" height="11" rx="2" />
            <path d="M12 14v3" />
          </svg>
        </div>
        <p className="eyebrow">加密文件管理系统</p>
        <h1>地基已经打好</h1>
        <p className="lede">
          第 1 阶段 · 项目骨架与基础设施。前后端已经连通，安全基础也准备好了。
        </p>
      </header>

      <main>
        <section className="status-card" aria-live="polite">
          <div className="status-heading">
            <span className={`status-dot status-${health.kind}`} aria-hidden="true" />
            <div>
              <p className="status-label">系统状态</p>
              <h2>{statusLabel}</h2>
            </div>
            <button
              className="refresh-button"
              type="button"
              onClick={refreshHealth}
              disabled={isLoading}
            >
              {isLoading ? '检查中…' : '刷新状态'}
            </button>
          </div>

          {health.kind === 'error' && <p className="error-text">{health.message}</p>}
          {health.kind === 'ok' && (
            <p className="ok-text">
              前端已成功调用后端接口，数据库连接正常。后续阶段会在这里加入登录和文件功能。
            </p>
          )}
          {isLoading && <p className="muted-text">正在连接本地后端，请稍候。</p>}

          <div className="meta-row">
            <span>接口地址</span>
            <code>{healthUrl}</code>
          </div>
          {lastChecked && (
            <div className="meta-row">
              <span>最近检查</span>
              <span>{lastChecked}</span>
            </div>
          )}
        </section>

        <section className="cards" aria-label="基础状态">
          <article className="info-card">
            <p className="card-label">后端</p>
            <p className="card-value">
              {health.kind === 'ok' ? '已连接' : health.kind === 'loading' ? '检查中' : '未连接'}
            </p>
            <p className="card-note">Django API · 仅本机开发访问</p>
          </article>
          <article className="info-card">
            <p className="card-label">数据库</p>
            <p className="card-value">
              {health.kind === 'ok' && health.data.database === 'ok'
                ? '正常'
                : health.kind === 'loading'
                  ? '检查中'
                  : '不可用'}
            </p>
            <p className="card-note">SQLite · 数据目录未进入版本库</p>
          </article>
          <article className="info-card">
            <p className="card-label">当前版本</p>
            <p className="card-value">
              {health.kind === 'ok' ? health.data.version : '0.1.0'}
            </p>
            <p className="card-note">第 1 阶段 · 项目骨架</p>
          </article>
        </section>

        <section className="notice">
          <h2>这一阶段还不会做的事</h2>
          <p>
            本阶段只验证“地基”是否稳固。登录、用户组、文件上传、加密和桌面客户端都在后续阶段，
            按 spec 逐步加入。现在系统只能在本机访问，请不要把它开放到局域网或公网。
          </p>
          <ul>
            <li>还不能登录或创建用户。</li>
            <li>还不能上传文件或保存密码。</li>
            <li>还不能安装桌面客户端。</li>
          </ul>
        </section>
      </main>

      <footer>
        <span>本地开发预览</span>
        <span>第 1 阶段 / 共 9 个阶段</span>
      </footer>
    </div>
  )
}

export default App
