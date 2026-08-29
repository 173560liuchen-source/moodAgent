# moodAgent

面向心理陪伴场景的多智能体系统。项目整合网页前端、Java 业务服务与 Python AI 服务，提供情绪识别、风险评估、对话辅助、知识检索（RAG）与干预跟进能力。

> 本项目用于学习、研究与原型验证，不替代心理咨询、医疗诊断或紧急救援服务。若出现自伤、自杀或其他紧急风险，请立即联系当地急救机构、危机干预热线或可信赖的专业人士。

## 项目结构

| 目录 | 说明 |
| --- | --- |
| `1/` | Web 前端页面与端到端测试 |
| `moodapp/demo/` | Java Spring Boot 业务后端 |
| `moodappPython/` | Python 多智能体与 RAG 服务 |
| `moodappPython/knowledge/` | 本地知识库资料 |
| `moodappPython/tests/` | Python 自动化测试 |
| `RUN.md` | Windows 本地运行说明 |
| `ENVIRONMENT.example` | 环境变量配置模板 |

## 技术组成

- 前端：HTML、JavaScript、Playwright
- 业务服务：Java、Spring Boot、Maven
- AI 服务：Python、FastAPI、Uvicorn
- 基础设施：MySQL、PostgreSQL、Redis（运行 Java 服务时需要）

## 快速开始

### 1. 准备依赖

启动 MySQL、PostgreSQL 和 Redis，并构建 Java 服务：

```powershell
cd moodapp\demo
mvn package -DskipTests
```

创建 Python 虚拟环境并安装依赖：

```powershell
cd ..\..\moodappPython
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### 2. 配置环境变量

将 `ENVIRONMENT.example` 复制为项目根目录的 `.env`，再填写模型服务密钥等配置：

```powershell
Copy-Item ENVIRONMENT.example .env
```

`.env` 包含敏感信息，已被 Git 忽略，请勿提交或公开。

### 3. 启动服务

在项目根目录运行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\start-all.ps1
```

前端默认访问地址为 <http://127.0.0.1:5500/index.html>。

停止服务：

```powershell
.\stop-all.ps1
```

运行日志与进程信息保存在 `.runtime/`，该目录不会提交到 Git。

## 开发与验证

Python 服务测试：

```powershell
cd moodappPython
python -m unittest discover -s tests -v
```

前端冒烟测试：

```powershell
cd 1
npm install
npm run test:smoke
```

Python 服务默认监听 `http://127.0.0.1:8081`，健康检查接口为 `GET /health`。更多运行细节请见 [RUN.md](RUN.md) 与 [Python 服务说明](moodappPython/README.md)。

## 安全与隐私

- 不要在 Issue、提交记录或日志中粘贴 API 密钥、访问令牌、用户聊天内容或可识别个人信息。
- 知识库内容与评估结果应在符合数据来源授权和隐私要求的前提下使用。
- 对模型输出应保留人工复核与必要的危机升级流程。

## 许可证

当前仓库尚未指定开源许可证。未经版权所有者明确授权，请勿将代码或资料用于超出学习、研究与演示范围的用途。
