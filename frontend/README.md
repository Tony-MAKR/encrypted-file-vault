# 前端（React + TypeScript + Vite）

这是加密文件管理系统的网页端，桌面客户端也加载同一套页面。

## 本地开发

从项目根目录运行一键脚本：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1
```

或在本目录手动运行：

```powershell
npm install
npm run dev
```

- 开发时前端地址：`http://127.0.0.1:5173`
- 开发时后端地址：`http://127.0.0.1:8000`（由 `VITE_API_BASE_URL` 指定）

## 生产构建

```powershell
npm run build
```

构建结果在 `frontend/dist`。后端用 WhiteNoise 直接提供这些文件，浏览器和桌面客户端访问同一个服务器地址；生产构建默认使用同源 API，不再跨域。

日常使用请在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

然后打开 `http://127.0.0.1:8000/`。

## 常用命令

```powershell
npm run build   # 类型检查 + 生产构建
npm run lint    # Oxlint 代码检查
npm run preview # 仅预览静态文件，不含后端接口
```

如需在开发时修改后端地址，复制 `.env.example` 为 `.env`，修改 `VITE_API_BASE_URL` 后重启开发服务器。生产构建不要设置该变量，否则会退回跨域请求。

## 功能范围

当前包含首次设置、登录、修改密码、用户管理、用户组与授权、文字秘密、文件加密上传/下载、分类/标签、搜索筛选、主页统计、密码生成器、回收站永久删除、审计日志查询、加密备份创建/验证和备份状态提醒。桌面客户端和网页端共用这些页面。
