# 贡献指南

感谢你愿意参与这个项目。它是一个面向 Windows 本机/局域网的加密文件与敏感信息管理工具，数据安全优先于开发速度。

## 开始之前

- 请不要在 Issue、Pull Request、测试或示例中加入真实密码、密钥、客户资料或生产数据。
- 安全问题不要公开提交 Issue，请按 [SECURITY.md](SECURITY.md) 的私密渠道报告。
- 本项目采用 [Apache-2.0](LICENSE)。提交贡献即表示你同意按同一许可证提供你的贡献。

## 开发环境

- Windows 10/11
- Python 3.12+（开发环境使用 3.14）
- Node.js LTS（开发环境使用 24）和 npm
- Git

首次安装：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup-dev.ps1
```

启动开发环境：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1
```

日常使用（由后端同时提供网页）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

## 本地检查

提交前至少运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check.ps1
```

包含：

- 后端 pytest 和 Ruff；
- 前端 TypeScript 构建和 Oxlint；
- 桌面端 JavaScript 单元测试。

浏览器端到端测试（需要先构建前端，且本机安装 Edge）：

```powershell
cd e2e
npm install
npm test
```

完整的测试说明见 [docs/testing.md](docs/testing.md)。

## 代码风格

- Python：Ruff 配置在 `backend/pyproject.toml`，行宽 100。
- 前端：TypeScript + React 函数组件，Oxlint 检查。
- 桌面端：CommonJS JavaScript，保持主进程/预加载/本地页面边界清晰。
- 注释解释“为什么”，不要重复代码表面行为。
- 不在日志、审计记录或错误信息中输出密码、主密码、密钥、令牌或明文内容。

## 提交 Pull Request

1. 从 `main` 创建分支，分支名建议 `feat/...`、`fix/...`、`docs/...`。
2. 保持改动聚焦，避免顺手重排无关代码。
3. 补充或更新测试；行为变化必须说明原因。
4. 更新相关文档和 `CHANGELOG.md`（面向用户的变更）。
5. 在 Pull Request 中写清：
   - 改了什么；
   - 为什么改；
   - 如何验证；
   - 是否涉及数据迁移、权限或加密行为。
6. 涉及数据库、密钥、权限或备份策略的改动，必须单独说明迁移和回滚方案。

## 数据安全红线

- 不删除、不覆盖用户数据；破坏性操作必须先确认并提供备份/回滚。
- 修改数据结构必须使用 Django 迁移，并在有真实数据的副本上演练。
- 测试必须使用临时数据库、临时密钥目录和临时备份目录。
- 不把 `.env`、`data/`、日志、备份、密钥或真实密文提交到仓库。

## 问题与讨论

- 功能建议和普通 Bug：使用 GitHub Issue 模板。
- 安全问题：使用 [SECURITY.md](SECURITY.md) 的私密报告方式。
- 提交前请确认没有包含个人隐私或第三方受限代码。
