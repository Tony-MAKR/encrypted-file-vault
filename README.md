# 加密文件管理系统

一个本地部署的加密文件与敏感信息管理系统的长期项目。管理员可以加密保存文件、网站账号、数据库密码等内容，并按用户组或单个用户授权；只有被授权的人可以查看和解密。

> **当前状态：第 1 阶段已完成“项目骨架与基础设施”。**  
> 登录、用户组、文件上传、加密和桌面客户端尚未实现，将按阶段逐步加入。  
> 现在系统只在本机开发环境中使用，**不要开放到局域网或公网**。

## 当前能做什么

- 后端 Django 服务可启动，健康检查接口可用。
- 前端 React 页面可启动，能显示后端和数据库状态。
- 配置、密钥、数据目录与代码分离，真实 `.env` 不进版本库。
- SQLite 数据库可迁移，日志可轮转并自动隐藏密码/令牌等敏感字段。
- 后端测试、代码检查和前端构建可通过。

## 当前不能做什么

- 不能登录或创建用户。
- 不能上传文件、保存密码或解密。
- 没有用户组、授权、审计业务日志和备份恢复。
- 没有桌面客户端、手机 App 或公网访问。
- 没有 HTTPS 和局域网部署配置。

## 环境要求

- Windows 10/11
- Python 3.12+（当前开发环境为 3.14.6）
- Node.js LTS + npm（当前开发环境为 Node 24.16 / npm 11.13）
- Git（可选，用于版本管理）

## 一键安装

在项目根目录打开 PowerShell，运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup-dev.ps1
```

脚本会：

1. 在 `backend/.venv` 创建独立 Python 环境（不改动系统 Python）。
2. 安装后端运行和测试依赖。
3. 生成随机密钥并写入 `.env`（不会显示、不会提交）。
4. 创建本地 SQLite 数据库并执行迁移。
5. 安装前端依赖到 `frontend/node_modules`。

## 启动

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1
```

会打开两个 PowerShell 窗口：

- 后端：`http://127.0.0.1:8000/api/v1/health/`
- 前端：`http://127.0.0.1:5173`

前端页面应显示“后端连接正常”。关闭这两个窗口即可停止服务。

## 自动检查

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check.ps1
```

包含后端 pytest、Ruff 检查、前端生产构建和 Oxlint 检查。

## 手动启动（便于排查）

```powershell
# 后端
cd backend
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000

# 前端（另开一个窗口）
cd frontend
npm run dev
```

## 目录说明

```text
backend/       Django 后端（配置、健康检查、测试）
frontend/      React + TypeScript + Vite 前端
docs/          可行性研究、需求分析、阶段 spec
scripts/       Windows 安装/启动/检查脚本
data/          本地数据库、日志和未来加密文件（不进入 Git）
.env           本地配置与随机密钥（不进入 Git）
```

## 安全说明（第 1 阶段）

- 后端开发服务器只监听 `127.0.0.1`，不接受局域网访问。
- `.env`、`data/`、虚拟环境、`node_modules` 都已被 `.gitignore` 忽略。
- 日志会隐藏 `password=`、`token=`、`Authorization: Bearer ...` 等敏感值；测试覆盖了这些规则。
- 数据库和日志放在 `data/`，不在前端静态目录下，不能通过浏览器 URL 直接下载。
- 当前没有登录，**绝对不要**把开发服务器改到 `0.0.0.0` 或开放到公网。

## 文档

- [项目立项与需求确认](docs/00-project-charter.md)
- [可行性研究报告](docs/01-feasibility-study.md)
- [需求分析说明书](docs/02-requirements-analysis.md)
- [第 1 阶段 spec](docs/specs/01-project-foundation.md)

## 后续阶段

账号与角色 → 用户组与授权 → 加密存储引擎 → Web 端功能 → 桌面客户端 → 审计与备份 → 测试与开源准备。每个阶段先写 spec，经确认后再开发。

## 开源准备

项目计划后续在 GitHub 开源。当前阶段尚未选择许可证；在发布前会单独确认许可证、补充英文 README、安全策略和贡献指南，并进行密钥/隐私扫描。
