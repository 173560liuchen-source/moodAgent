# 真实端到端测试

`LiveAgentEndToEndTests` 会写入聊天与分析记录，因此只能连接独立测试数据库，不能连接演示或生产数据库。

运行前：

1. 启动 Python Agent 服务和 Java 后端；
2. 配置后端使用独立测试数据库；
3. 在测试库中准备一个专用测试用户；
4. 设置环境变量后运行测试。

```powershell
$env:MOODAPP_E2E="true"
$env:MOODAPP_E2E_USER_ID="测试用户ID"
$env:MOODAPP_E2E_BASE_URL="http://127.0.0.1:8080"
mvn test -Dtest=LiveAgentEndToEndTests
```

测试使用固定的 `session_id=e2e-live-session` 和 `request_id=e2e-live-request`。运行后应按这两个标识清理测试库产生的聊天、分析和审计记录。
