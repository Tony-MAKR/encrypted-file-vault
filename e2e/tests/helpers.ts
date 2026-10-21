import { expect, type Page } from '@playwright/test'

export const ADMIN = {
  username: 'e2e_admin',
  displayName: 'E2E 管理员',
  password: 'Stage8-Admin-Password-2026!',
}

export const USER = {
  username: 'e2e_user',
  displayName: 'E2E 普通用户',
  tempPassword: 'Stage8-User-Temp-Password-2026!',
  password: 'Stage8-User-Final-Password-2026!',
}

export const MASTER_PASSWORD = 'Stage8-Master-Password-2026!'
export const BACKUP_PASSPHRASE = 'Stage8-Backup-Passphrase-2026!'
export const ITEM_TITLE = 'E2E 数据库密码'
export const SECRET_VALUE = 'E2E-Secret-Value-2026!'

export async function login(
  page: Page,
  username: string,
  password: string,
): Promise<void> {
  await page.goto('/login')
  await page.locator('#username').fill(username)
  await page.locator('#password').fill(password)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(
    page.getByRole('heading', { name: /欢迎回来/ }),
  ).toBeVisible()
}

export async function logout(page: Page): Promise<void> {
  await page.getByRole('button', { name: '退出' }).click()
  await expect(page).toHaveURL(/\/login$/)
}

interface ApiResult<T = unknown> {
  status: number
  data: T
}

export async function api<T = unknown>(
  page: Page,
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE',
  path: string,
  body?: unknown,
): Promise<ApiResult<T>> {
  return page.evaluate(
    async ({ method, path, body }) => {
      const match = document.cookie
        .split('; ')
        .find((row) => row.startsWith('csrftoken='))
      const token = match
        ? decodeURIComponent(match.slice('csrftoken='.length))
        : ''
      const response = await fetch(path, {
        method,
        credentials: 'include',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          'X-CSRFToken': token,
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      })
      let data: unknown = null
      try {
        data = await response.json()
      } catch {
        data = null
      }
      return { status: response.status, data }
    },
    { method, path, body },
  ) as Promise<ApiResult<T>>
}
