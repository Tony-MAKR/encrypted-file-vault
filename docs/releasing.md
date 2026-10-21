# 发布流程

本文档面向维护者，说明如何准备和发布一个新版本。默认只做本地准备，不自动推送 GitHub。

## 1. 确定版本号

版本号使用语义化版本：`主版本.次版本.修订号`。

需要同步修改：

- `backend/config/settings.py` 的 `APP_VERSION`
- `frontend/package.json` 的 `version`
- `desktop/package.json` 的 `version`
- `CHANGELOG.md` 增加对应版本条目

```powershell
cd frontend
npm version 1.0.1 --no-git-tag-version

cd ..\desktop
npm version 1.0.1 --no-git-tag-version
```

后端 `APP_VERSION` 手动修改。三个版本号必须一致。

## 2. 发布前检查

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check.ps1
```

再运行浏览器测试：

```powershell
cd e2e
npm ci
npm test
```

完成 [docs/testing.md](testing.md) 中的发布前人工验收清单。

## 3. 安全检查

```powershell
cd backend
.venv\Scripts\python.exe manage.py security_check
```

并执行 [docs/testing.md](testing.md) 中的依赖漏洞扫描。

确认：

- `git status` 干净；
- 没有 `.env`、`data/`、日志、密钥、密文或备份进入版本库；
- Git 历史中没有真实秘密；
- 没有把测试密码替换成真实密码。

## 4. 构建发布文件

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build-desktop.ps1
```

产物在 `desktop/release/`：

- `EncryptedFileVault-Setup-<版本>-x64.exe`
- `EncryptedFileVault-Portable-<版本>-x64.zip`
- `SHA256SUMS.txt`
- `INSTALL.txt`

检查：

```powershell
cd desktop\release
Get-FileHash *.exe -Algorithm SHA256
Get-FileHash *.zip -Algorithm SHA256
Get-Content SHA256SUMS.txt
```

## 5. 发布演练

在临时目录或另一台电脑上：

1. 安装或解压新版本；
2. 启动 `scripts/start.ps1`；
3. 登录、解锁保险箱、查看一个条目；
4. 创建并验证一个备份；
5. 在隔离数据目录执行一次恢复；
6. 卸载客户端，确认服务器数据仍在。

不要把演练用的临时数据或备份提交到仓库。

## 6. 提交和打标签

确认无误后，由维护者手动执行：

```powershell
git add -A
git commit -m "release: v1.0.0"
git tag -a v1.0.0 -m "v1.0.0"
```

**不要**在未确认的情况下推送标签或创建 Release。

## 7. 创建 GitHub Release

在 GitHub 仓库页面：

1. 选择标签 `v1.0.0`；
2. 标题写版本号；
3. 说明包含：
   - 主要功能和变更；
   - 升级方法；
   - 已知限制；
   - 安装包未签名和 SmartScreen 提示；
   - SHA-256 校验方法；
   - 安全边界和数据备份提醒。
4. 上传安装版、免安装版、`SHA256SUMS.txt`、`INSTALL.txt`；
5. 发布前再次核对文件校验值。

## 8. 回滚

- 客户端：重新安装上一版本安装包；服务器数据不受影响。
- 数据：使用 `scripts/restore-backup.ps1` 和最近的加密备份。
- 不删除旧版本安装包和旧备份；由维护者确认后再清理。

## 9. 发布后

- 观察 Issue 和安全报告；
- 及时更新依赖安全补丁；
- 在 `CHANGELOG.md` 记录后续版本；
- 不在客户端中加入自动下载或远程执行功能。
