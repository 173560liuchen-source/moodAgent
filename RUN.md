# MoodApp 本地运行

## 第一次准备

确保 MySQL、PostgreSQL、Redis 已启动，并先构建 Java：

```powershell
cd D:\moodA\moodapp\demo
mvn package -DskipTests
```

Python 依赖安装在 `moodappPython\.venv` 中；如果尚未安装：

```powershell
cd D:\moodA\moodappPython
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

如需配置模型，把 `ENVIRONMENT.example` 复制为 `D:\moodA\.env` 并填写密钥。启动脚本会自动加载它。

## 一键启动

在 PowerShell 执行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
D:\moodA\start-all.ps1
```

访问 `http://127.0.0.1:5500/index.html`。

## 一键停止

```powershell
D:\moodA\stop-all.ps1
```

日志和 PID 文件保存在 `D:\moodA\.runtime`。脚本不会停止 MySQL、PostgreSQL 或 Redis。
