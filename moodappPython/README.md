# MoodApp Agent Service

Python 多智能体服务，供现有 Java Spring Boot 后端调用。

## 第一步：启动健康检查

```powershell
python -m venv .venv
.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8081 --reload
```

访问 `http://127.0.0.1:8081/health`，应返回 `status: ok`。

当前版本不连接数据库或 Redis；模型调用通过统一网关完成。

## 自动化验证

```powershell
python -m unittest discover -s tests -v
```

测试覆盖危机识别、多轮上下文、RAG 检索与引用、故障降级和延迟优化。比赛使用的应用成效采集模板及当前技术证据位于 `docs/competition/`。

## 第二步：配置统一模型API

在项目根目录创建 `.env` 文件：

```dotenv
MODEL_API_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MODEL_API_KEY=你的API密钥
MODEL_NAME=qwen-turbo
MODEL_TIMEOUT_SECONDS=120
```


启动服务后，调用 `POST http://127.0.0.1:8081/v1/model/chat`。

如果使用本地OpenAI兼容服务，只需要把 `MODEL_API_BASE_URL` 改成本地地址，Python代码无需修改。

## 响应性能与降级

服务会复用模型、Embedding 与重排请求的 HTTP 连接；普通情绪分析、知识检索和对话生成分别设置独立超时。知识检索超时或模型不可用时会返回结构化降级结果，不阻塞安全检查。

关键参数可在 `.env` 中调整：

```dotenv
MOODAPP_CRISIS_MODEL_TIMEOUT_SECONDS=3
RAG_REQUEST_TIMEOUT_SECONDS=2
EMOTION_REQUEST_TIMEOUT_SECONDS=2.5
CHAT_REQUEST_TIMEOUT_SECONDS=7
RAG_CACHE_MAX_ENTRIES=512
RAG_CACHE_TTL_SECONDS=1800
```

运行性能基准：

```powershell
python scripts/run_performance.py --requests 20 --concurrency 2 --output reports/evaluation/performance.json
```

报告同时给出平均值、P50、P95、各节点耗时和降级请求比例。小样本结果仅用于开发回归，答辩材料应使用固定测试集并至少重复三轮。
