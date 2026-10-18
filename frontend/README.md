# 前端（React + TypeScript + Vite）

这是加密文件管理系统的网页端。第 2 阶段包含首次设置、登录、修改密码、主页和管理员用户管理页面。

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
后端地址：`http://127.0.0.1:8000`

首次使用时，如果数据库里还没有管理员，页面会显示“创建第一位管理员”。请在本机完成设置；设置成功后入口会自动关闭。

## 常用命令

```powershell
npm run build   # 类型检查 + 生产构建
npm run lint    # Oxlint 代码检查
npm run preview # 预览构建结果
```

如需修改后端地址，复制 `.env.example` 为 `.env`，修改 `VITE_API_BASE_URL` 后重启开发服务器。

## 当前不包含

文件上传、加密存储、用户组、内容授权和桌面客户端仍在后续阶段。请不要把真实敏感资料放到当前版本。
