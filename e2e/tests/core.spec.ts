import { expect, test } from '@playwright/test'

import {
  ADMIN,
  BACKUP_PASSPHRASE,
  ITEM_TITLE,
  MASTER_PASSWORD,
  SECRET_VALUE,
  USER,
  api,
  login,
  logout,
} from './helpers'

test.describe.serial('core flows', () => {
  let userId = 0
  let itemId = 0

  test('first-run setup and login', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/\/setup$/)

    await page.locator('input[name="username"]').fill(ADMIN.username)
    await page.locator('input[name="display_name"]').fill(ADMIN.displayName)
    await page.locator('input[name="password"]').fill(ADMIN.password)
    await page
      .locator('input[name="password_confirm"]')
      .fill(ADMIN.password)
    await page.getByRole('button', { name: '创建管理员' }).click()

    await expect(page).toHaveURL(/\/login$/)
    await login(page, ADMIN.username, ADMIN.password)
    await expect(page.getByText('备份状态')).toBeVisible()
  })

  test('normal user cannot see admin pages', async ({ page }) => {
    await login(page, ADMIN.username, ADMIN.password)

    const created = await api<{ id: number }>(page, 'POST', '/api/v1/admin/users/', {
      username: USER.username,
      display_name: USER.displayName,
      password: USER.tempPassword,
      password_confirm: USER.tempPassword,
      role: 'user',
    })
    expect(created.status).toBe(201)
    userId = created.data.id

    await logout(page)

    await page.goto('/login')
    await page.locator('#username').fill(USER.username)
    await page.locator('#password').fill(USER.tempPassword)
    await page.getByRole('button', { name: '登录' }).click()
    await expect(page).toHaveURL(/\/change-password$/)

    await page.locator('input[name="current_password"]').fill(USER.tempPassword)
    await page.locator('input[name="new_password"]').fill(USER.password)
    await page
      .locator('input[name="new_password_confirm"]')
      .fill(USER.password)
    await page.getByRole('button', { name: '保存新密码' }).click()
    await expect(
      page.getByRole('heading', { name: /欢迎回来/ }),
    ).toBeVisible()

    await expect(page.getByRole('link', { name: '用户管理' })).toHaveCount(0)
    await expect(page.getByRole('link', { name: '审计日志' })).toHaveCount(0)
    await expect(page.getByRole('link', { name: '备份恢复' })).toHaveCount(0)

    await page.goto('/admin/audit')
    await expect(page).toHaveURL(/\/$/)

    await logout(page)
    await login(page, ADMIN.username, ADMIN.password)
  })

  test('encrypted text secret is visible only to the granted user', async ({
    page,
  }) => {
    await login(page, ADMIN.username, ADMIN.password)

    const initialized = await api(page, 'POST', '/api/v1/vault/initialize/', {
      master_password: MASTER_PASSWORD,
      master_password_confirm: MASTER_PASSWORD,
    })
    expect(initialized.status).toBe(201)

    const item = await api<{ id: number }>(page, 'POST', '/api/v1/admin/items/', {
      title: ITEM_TITLE,
      item_type: 'text',
      description: 'Playwright 测试条目',
      category: '测试',
      tags: ['e2e'],
    })
    expect(item.status).toBe(201)
    itemId = item.data.id

    const saved = await api(
      page,
      'PUT',
      `/api/v1/admin/items/${itemId}/content/text/`,
      {
        url: 'https://example.test',
        username: 'demo-user',
        password: SECRET_VALUE,
        notes: '仅用于端到端测试',
      },
    )
    expect(saved.status).toBe(200)

    const grant = await api(
      page,
      'POST',
      `/api/v1/admin/items/${itemId}/grants/users/`,
      { user_ids: [userId] },
    )
    expect(grant.status).toBe(201)

    await logout(page)
    await login(page, USER.username, USER.password)

    await page.goto('/items')
    await page.getByRole('link', { name: ITEM_TITLE }).click()
    await expect(
      page.getByRole('heading', { name: ITEM_TITLE }),
    ).toBeVisible()
    await page.getByRole('button', { name: '显示密码' }).click()
    await expect(page.getByText(SECRET_VALUE)).toBeVisible()

    await logout(page)
    await login(page, ADMIN.username, ADMIN.password)
  })

  test('audit log shows key operations', async ({ page }) => {
    await login(page, ADMIN.username, ADMIN.password)
    await page.goto('/admin/audit')

    await expect(page.getByRole('heading', { name: '审计日志' })).toBeVisible()
    const auditRows = page.locator('.audit-table tbody')
    await expect(auditRows.getByText('登录成功').first()).toBeVisible()
    await expect(auditRows.getByText('创建条目').first()).toBeVisible()
    await expect(auditRows.getByText('保存文字秘密').first()).toBeVisible()
    await expect(auditRows.getByText('显示密码').first()).toBeVisible()

    await page.getByLabel('操作类别').selectOption('auth')
    await expect(auditRows.getByText('登录成功').first()).toBeVisible()
  })

  test('encrypted backup can be created and verified', async ({ page }) => {
    await login(page, ADMIN.username, ADMIN.password)
    await page.goto('/admin/backup')

    await page.locator('#backup-passphrase').fill(BACKUP_PASSPHRASE)
    await page.locator('#backup-confirm').fill(BACKUP_PASSPHRASE)
    await page.locator('#backup-note').fill('Playwright 测试备份')
    await page.getByRole('button', { name: '创建备份' }).click()

    await expect(
      page.locator('.form-success').filter({ hasText: '备份已创建' }),
    ).toBeVisible({ timeout: 60_000 })
    await expect(page.getByText('vault-backup-').first()).toBeVisible()

    await page.getByRole('button', { name: '验证' }).first().click()
    await page.locator('#verify-passphrase').fill(BACKUP_PASSPHRASE)
    await page.getByRole('button', { name: '开始验证' }).click()

    await expect(
      page.locator('.form-success').filter({ hasText: '备份验证通过' }),
    ).toBeVisible({ timeout: 60_000 })
    await expect(page.getByText('已验证').first()).toBeVisible()
  })
})
