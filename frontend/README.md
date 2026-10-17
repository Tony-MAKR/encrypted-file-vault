# 前端（React + TypeScript + Vite）

这是加密文件管理系统的网页端。第 1 阶段只包含项目骨架和健康检查页面，还没有登录、上传或加密功能。

## 本地启动

从项目根目录运行一键脚本：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1
```

或在本目录手动运行：

```powershell
npm install
npm run dev
```

前端默认地址：`http://127.0.0.1:5173`  
后端健康检查：`http://127.0.0.1:8000/api/v1/health/`

## 常用命令

```powershell
npm run build   # 类型检查 + 生产构建
npm run lint    # Oxlint 代码检查
npm run preview # 预览构建结果
```

如需修改后端地址，复制 `.env.example` 为 `.env`，修改 `VITE_API_BASE_URL` 后重启开发服务器。
