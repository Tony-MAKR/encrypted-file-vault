# 测试说明

本文档说明本地和 CI 如何测试本项目。测试使用临时数据库、临时密钥目录和临时备份目录，不会接触真实 `.env` 或 `data/`。

## 一键检查

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check.ps1
```

包含：

1. 后端 pytest；
2. 后端 Ruff；
3. 前端 TypeScript 构建；
4. 前端 Oxlint；
5. 桌面端单元测试（已安装依赖时）。

## 后端测试

```powershell
cd backend
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check .
```

- 测试数据库由 pytest-django 自动创建和销毁。
- `tests/conftest.py` 会把密钥、密文、临时文件和备份目录指向 `tmp_path`。
- 测试中的密码、主密码和备份口令都是虚构值，不得替换为真实值。
- 覆盖率报告（可选）：

```powershell
.venv\Scripts\python.exe -m pytest --cov=apps --cov-report=html
```

报告输出到 `htmlcov/`，该目录已被 `.gitignore` 忽略。

## 前端检查

```powershell
cd frontend
npm ci
npm run build
npm run lint
```

## 桌面端检查

```powershell
cd desktop
npm ci
npm test
```

Electron 冒烟测试（需要构建后的网页和运行中的服务器）：

```powershell
npm run smoke
```

安装、卸载和下载对话框属于人工验收，不在单元测试中自动执行。

## 浏览器端到端测试

需要 Windows、Node.js、已安装 Microsoft Edge，并先构建前端。

```powershell
cd e2e
npm ci
npm test
```

`e2e/playwright.config.ts` 会：

- 在系统临时目录创建独立 `DATA_DIR`；
- 执行数据库迁移；
- 在 `127.0.0.1:8020` 启动临时服务器；
- 测试结束后删除临时数据目录。

核心路径：

1. 首次设置管理员并登录；
2. 普通用户看不到管理员入口和未授权内容；
3. 管理员初始化保险箱、保存文字秘密、授权用户，用户查看并显示密码；
4. 审计日志可以看到关键操作；
5. 创建并验证加密备份。

测试不记录密码输入值，不生成包含请求体的跟踪文件。

## 发布前人工验收

自动化测试之外，发布前至少完成：

- [ ] 全新安装，创建首位管理员并登录。
- [ ] 创建普通用户、用户组，添加/移出成员。
- [ ] 创建文字条目，设置分类/标签，用筛选和搜索找到它。
- [ ] 保存文字秘密，授权用户查看、显示/复制密码。
- [ ] 上传文件、下载文件，检查原始文件名和内容。
- [ ] 删除到回收站、恢复、永久删除。
- [ ] 初始化/解锁/锁定保险箱；服务器重启后确认自动锁定。
- [ ] 审计日志能查到上述关键操作，详情不含秘密。
- [ ] 创建备份、验证备份；在临时数据目录做一次恢复演练。
- [ ] 安装桌面客户端、连接服务器、登录、下载；卸载后服务器数据仍在。
- [ ] 960×640 窗口下页面没有横向溢出。
- [ ] 运行 `manage.py security_check`，确认没有失败项。

## 安全扫描

```powershell
# Python 依赖漏洞
cd backend
.venv\Scripts\python.exe -m pip install pip-audit
.venv\Scripts\python.exe -m pip_audit -r requirements.txt

# 前端运行时依赖
cd frontend
npm audit --omit=dev --audit-level=high

# 桌面运行时依赖（Electron 打包后运行时）
cd desktop
npm audit --omit=dev --audit-level=high
```

发布前还要确认：

- `git status` 没有真实 `.env`、`data/`、日志、密钥、密文或备份；
- Git 历史中没有真实密钥或用户数据；
- `DJANGO_DEBUG=false`，`ALLOWED_HOSTS` 没有通配符；
- 安装包和 `SHA256SUMS.txt` 一致。

如果发现真实秘密进入 Git 历史，先停止发布并告知维护者；改写历史属于破坏性操作，不能擅自执行。
