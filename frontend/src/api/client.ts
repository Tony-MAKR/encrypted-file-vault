export type UserRole = 'admin' | 'user'

export interface User {
  id: number
  username: string
  display_name: string
  role: UserRole
  is_active: boolean
  must_change_password: boolean
  is_locked: boolean
  last_login: string | null
  date_joined: string
  created_at: string
  updated_at: string
  created_by: string | null
}

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface SetupPayload {
  username: string
  display_name: string
  password: string
  password_confirm: string
}

export interface CreateUserPayload extends SetupPayload {
  role: UserRole
}

export interface ResetPasswordPayload {
  new_password: string
  new_password_confirm: string
}

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'
).replace(/\/$/, '')

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])
const FIELD_LABELS: Record<string, string> = {
  username: '用户名',
  display_name: '显示名',
  password: '密码',
  password_confirm: '确认密码',
  current_password: '当前密码',
  new_password: '新密码',
  new_password_confirm: '确认新密码',
  role: '角色',
  detail: '',
  non_field_errors: '',
}

export const UNAUTHORIZED_EVENT = 'vault:unauthorized'

export class ApiError extends Error {
  readonly status: number
  readonly data: unknown

  constructor(status: number, data: unknown) {
    super(extractErrorMessage(data) || '请求失败，请稍后再试。')
    this.name = 'ApiError'
    this.status = status
    this.data = data
  }
}

export function extractErrorMessage(data: unknown): string {
  if (typeof data === 'string') {
    return data
  }
  if (Array.isArray(data)) {
    return data
      .map((item) => extractErrorMessage(item))
      .filter(Boolean)
      .join('；')
  }
  if (data && typeof data === 'object') {
    const record = data as Record<string, unknown>
    if (typeof record.detail === 'string') {
      return record.detail
    }
    for (const [key, value] of Object.entries(record)) {
      const message = extractErrorMessage(value)
      if (!message) {
        continue
      }
      const label = FIELD_LABELS[key]
      return label ? `${label}：${message}` : message
    }
  }
  return ''
}

function readCookie(name: string): string | null {
  const prefix = `${name}=`
  const row = document.cookie
    .split('; ')
    .find((item) => item.startsWith(prefix))
  if (!row) {
    return null
  }
  return decodeURIComponent(row.slice(prefix.length))
}

async function fetchCsrfToken(): Promise<string | null> {
  await fetch(`${API_BASE_URL}/api/v1/auth/csrf/`, {
    method: 'GET',
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  return readCookie('csrftoken')
}

async function ensureCsrfToken(): Promise<string | null> {
  return readCookie('csrftoken') ?? fetchCsrfToken()
}

export async function primeCsrfToken(): Promise<void> {
  await ensureCsrfToken()
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase()
  const headers = new Headers(options.headers)
  headers.set('Accept', 'application/json')

  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  if (!SAFE_METHODS.has(method)) {
    const token = await ensureCsrfToken()
    if (token) {
      headers.set('X-CSRFToken', token)
    }
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      method,
      headers,
      credentials: 'include',
    })
  } catch {
    throw new ApiError(0, {
      detail: '无法连接后端，请确认服务已启动。',
    })
  }

  if (response.status === 401) {
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
  }

  if (response.status === 204) {
    return undefined as T
  }

  const contentType = response.headers.get('content-type') ?? ''
  const data: unknown = contentType.includes('application/json')
    ? await response.json()
    : await response.text()

  if (!response.ok) {
    throw new ApiError(response.status, data)
  }

  return data as T
}

export const authApi = {
  setupStatus: () =>
    apiFetch<{ needs_setup: boolean }>('/api/v1/setup/status/'),

  setup: (payload: SetupPayload) =>
    apiFetch<User>('/api/v1/setup/', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  login: (username: string, password: string) =>
    apiFetch<User>('/api/v1/auth/login/', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),

  logout: () =>
    apiFetch<void>('/api/v1/auth/logout/', {
      method: 'POST',
    }),

  me: () => apiFetch<User>('/api/v1/auth/me/'),

  changePassword: (payload: {
    current_password: string
    new_password: string
    new_password_confirm: string
  }) =>
    apiFetch<{ detail: string }>('/api/v1/auth/change-password/', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
}

export const adminApi = {
  listUsers: ({
    page = 1,
    q = '',
    pageSize = 20,
  }: {
    page?: number
    q?: string
    pageSize?: number
  } = {}) =>
    apiFetch<Paginated<User>>(
      `/api/v1/admin/users/?page=${page}&page_size=${pageSize}&q=${encodeURIComponent(q)}`,
    ),

  createUser: (payload: CreateUserPayload) =>
    apiFetch<User>('/api/v1/admin/users/', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  updateDisplayName: (userId: number, displayName: string) =>
    apiFetch<User>(`/api/v1/admin/users/${userId}/`, {
      method: 'PATCH',
      body: JSON.stringify({ display_name: displayName }),
    }),

  setRole: (userId: number, role: UserRole) =>
    apiFetch<User>(`/api/v1/admin/users/${userId}/role/`, {
      method: 'POST',
      body: JSON.stringify({ role }),
    }),

  disable: (userId: number) =>
    apiFetch<User>(`/api/v1/admin/users/${userId}/disable/`, {
      method: 'POST',
    }),

  enable: (userId: number) =>
    apiFetch<User>(`/api/v1/admin/users/${userId}/enable/`, {
      method: 'POST',
    }),

  resetPassword: (userId: number, payload: ResetPasswordPayload) =>
    apiFetch<{ detail: string }>(
      `/api/v1/admin/users/${userId}/reset-password/`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),

  unlock: (userId: number) =>
    apiFetch<User>(`/api/v1/admin/users/${userId}/unlock/`, {
      method: 'POST',
    }),
}
