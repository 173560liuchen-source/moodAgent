package com.example.app.service.Impl;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import com.example.app.dto.python.PythonChatMessage;
import com.example.app.dto.python.PythonOrchestratorResponse;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;

@Service
public class PythonOrchestratorService {

    private static final MediaType JSON_MEDIA_TYPE =
            MediaType.parse("application/json; charset=utf-8");

    private final OkHttpClient client = new OkHttpClient.Builder()
            .connectTimeout(5, TimeUnit.SECONDS)
            .readTimeout(45, TimeUnit.SECONDS)
            .writeTimeout(5, TimeUnit.SECONDS)
            .build();

    @Value("${moodapp.agent.base-url:http://127.0.0.1:8081}")
    private String agentBaseUrl;

    @Value("${moodapp.agent.gateway-token:}")
    private String gatewayToken;

    public PythonOrchestratorResponse orchestrate(
            Long userId,
            String sessionId,
            String message,
            List<PythonChatMessage> history
    ) {
        return orchestrate(userId, sessionId, message, history, null);
    }

    public PythonOrchestratorResponse orchestrateStream(
            Long userId,
            String sessionId,
            String requestId,
            String message,
            List<PythonChatMessage> history,
            Map<String, Object> metadata,
            boolean proactiveGreeting,
            Consumer<String> onDelta
    ) {
        if (message == null || message.isBlank()) {
            throw new PythonOrchestratorException("message cannot be blank");
        }
        String path = proactiveGreeting
                ? "/v1/agents/greeting/stream"
                : "/v1/agents/orchestrate/stream";
        JSONObject body = buildRequestBody(userId, sessionId, requestId, message, history, metadata);
        Request request = requestBuilder(path)
                .header("Accept", "text/event-stream")
                .post(RequestBody.create(body.toJSONString(), JSON_MEDIA_TYPE))
                .build();

        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful() || response.body() == null) {
                throw new PythonOrchestratorException(
                        "Python streaming Orchestrator unavailable, status=" + response.code()
                );
            }
            PythonOrchestratorResponse result = null;
            String event = null;
            StringBuilder data = new StringBuilder();
            String line;
            while ((line = response.body().source().readUtf8Line()) != null) {
                if (line.isEmpty()) {
                    result = handleSseEvent(event, data.toString(), result, onDelta);
                    event = null;
                    data.setLength(0);
                } else if (line.startsWith("event:")) {
                    event = line.substring(6).trim();
                } else if (line.startsWith("data:")) {
                    if (data.length() > 0) {
                        data.append('\n');
                    }
                    data.append(line.substring(5).trim());
                }
            }
            if (data.length() > 0) {
                result = handleSseEvent(event, data.toString(), result, onDelta);
            }
            if (result == null || !result.hasReply()) {
                throw new PythonOrchestratorException("Python streaming Orchestrator returned empty reply");
            }
            return result;
        } catch (IOException ex) {
            throw new PythonOrchestratorException("Python streaming Orchestrator request failed", ex);
        }
    }

    private PythonOrchestratorResponse handleSseEvent(
            String event,
            String rawData,
            PythonOrchestratorResponse current,
            Consumer<String> onDelta
    ) {
        if (event == null || rawData == null || rawData.isBlank()) {
            return current;
        }
        JSONObject payload = JSON.parseObject(rawData);
        if ("delta".equals(event)) {
            String content = payload.getString("content");
            if (content != null && !content.isEmpty()) {
                onDelta.accept(content);
            }
        } else if ("result".equals(event)) {
            return JSON.parseObject(rawData, PythonOrchestratorResponse.class);
        } else if ("error".equals(event)) {
            throw new PythonOrchestratorException(
                    "Python streaming Orchestrator error: " + payload.getString("message")
            );
        }
        return current;
    }

    public PythonOrchestratorResponse orchestrate(
            Long userId,
            String sessionId,
            String message,
            List<PythonChatMessage> history,
            Map<String, Object> metadata
    ) {
        return orchestrate(userId, sessionId, null, message, history, metadata);
    }

    public PythonOrchestratorResponse orchestrate(
            Long userId,
            String sessionId,
            String requestId,
            String message,
            List<PythonChatMessage> history,
            Map<String, Object> metadata
    ) {
        if (message == null || message.isBlank()) {
            throw new PythonOrchestratorException("message cannot be blank");
        }

        JSONObject body = buildRequestBody(userId, sessionId, requestId, message, history, metadata);
        Request request = requestBuilder("/v1/agents/orchestrate")
                .post(RequestBody.create(body.toJSONString(), JSON_MEDIA_TYPE))
                .build();

        try (Response response = client.newCall(request).execute()) {
            String rawBody = response.body() == null ? "" : response.body().string();
            if (!response.isSuccessful()) {
                throw new PythonOrchestratorException(
                        "Python Orchestrator unavailable, status=" + response.code()
                );
            }
            if (rawBody.isBlank()) {
                throw new PythonOrchestratorException("Python Orchestrator returned empty body");
            }

            PythonOrchestratorResponse result =
                    JSON.parseObject(rawBody, PythonOrchestratorResponse.class);
            if (result == null || !result.hasReply()) {
                throw new PythonOrchestratorException("Python Orchestrator returned empty reply");
            }
            return result;
        } catch (IOException ex) {
            throw new PythonOrchestratorException("Python Orchestrator request failed", ex);
        } catch (RuntimeException ex) {
            if (ex instanceof PythonOrchestratorException pythonException) {
                throw pythonException;
            }
            throw new PythonOrchestratorException("Python Orchestrator response parse failed", ex);
        }
    }

    public JSONObject analyzeTrend(JSONArray points) {
        JSONObject body = new JSONObject();
        body.put("points", points == null ? new JSONArray() : points);
        return postJson("/v1/agents/trend", body);
    }

    public JSONObject assessRisk(
            JSONObject crisis,
            JSONObject emotion,
            JSONObject trend,
            JSONObject rag
    ) {
        JSONObject body = new JSONObject();
        body.put("crisis", crisis == null ? new JSONObject() : crisis);
        body.put("emotion", emotion == null ? new JSONObject() : emotion);
        body.put("trend", trend);
        body.put("rag", rag);
        return postJson("/v1/agents/risk", body);
    }

    public JSONObject health() {
        return getJson("/health");
    }

    public JSONObject ready() {
        return getJson("/health/ready");
    }

    public JSONObject modelStatus() {
        return getJson("/v1/metrics/model");
    }

    public JSONObject agentRegistry() {
        JSONObject result = new JSONObject();
        result.put("agents", getArray("/v1/agents/registry"));
        return result;
    }

    public JSONObject ragStatus() {
        return getJson("/v1/rag/status");
    }

    public JSONObject ragSearch(JSONObject body) {
        return postJson("/v1/rag/search", body == null ? new JSONObject() : body);
    }

    public JSONObject generateAssessmentReport(Integer score, String level, List<Integer> answers) {
        JSONObject body = new JSONObject();
        body.put("score", score);
        body.put("level", level == null || level.isBlank() ? "待评估" : level);
        body.put("answers", answers == null ? new JSONArray() : answers);
        return postJson("/v1/agents/assessment-report", body);
    }

    public JSONObject latestEvaluationSummary() {
        return getJson("/v1/evaluation/redteam/latest-summary");
    }

    public JSONObject latestEvaluationReport() {
        return getJson("/v1/evaluation/redteam/latest-report");
    }

    public JSONObject redteamCases() {
        JSONObject result = new JSONObject();
        result.put("cases", getArray("/v1/evaluation/redteam/cases"));
        return result;
    }

    private JSONObject getJson(String path) {
        Request request = requestBuilder(path)
                .get()
                .build();

        try (Response response = client.newCall(request).execute()) {
            String rawBody = response.body() == null ? "" : response.body().string();
            if (!response.isSuccessful()) {
                throw new PythonOrchestratorException(
                        "Python Agent unavailable, status=" + response.code()
                );
            }
            if (rawBody.isBlank()) {
                throw new PythonOrchestratorException("Python Agent returned empty body");
            }
            return JSON.parseObject(rawBody);
        } catch (IOException ex) {
            throw new PythonOrchestratorException("Python Agent request failed", ex);
        } catch (RuntimeException ex) {
            if (ex instanceof PythonOrchestratorException pythonException) {
                throw pythonException;
            }
            throw new PythonOrchestratorException("Python Agent response parse failed", ex);
        }
    }

    private JSONObject postJson(String path, JSONObject body) {
        Request request = requestBuilder(path)
                .post(RequestBody.create(body.toJSONString(), JSON_MEDIA_TYPE))
                .build();

        try (Response response = client.newCall(request).execute()) {
            String rawBody = response.body() == null ? "" : response.body().string();
            if (!response.isSuccessful()) {
                throw new PythonOrchestratorException(
                        "Python Agent unavailable, path=" + path + ", status=" + response.code()
                );
            }
            if (rawBody.isBlank()) {
                throw new PythonOrchestratorException("Python Agent returned empty body, path=" + path);
            }
            return JSON.parseObject(rawBody);
        } catch (IOException ex) {
            throw new PythonOrchestratorException("Python Agent request failed, path=" + path, ex);
        } catch (RuntimeException ex) {
            if (ex instanceof PythonOrchestratorException pythonException) {
                throw pythonException;
            }
            throw new PythonOrchestratorException("Python Agent response parse failed, path=" + path, ex);
        }
    }

    private JSONArray getArray(String path) {
        Request request = requestBuilder(path)
                .get()
                .build();

        try (Response response = client.newCall(request).execute()) {
            String rawBody = response.body() == null ? "" : response.body().string();
            if (!response.isSuccessful()) {
                throw new PythonOrchestratorException(
                        "Python Agent unavailable, path=" + path + ", status=" + response.code()
                );
            }
            if (rawBody.isBlank()) {
                throw new PythonOrchestratorException("Python Agent returned empty body, path=" + path);
            }
            return JSON.parseArray(rawBody);
        } catch (IOException ex) {
            throw new PythonOrchestratorException("Python Agent request failed, path=" + path, ex);
        } catch (RuntimeException ex) {
            if (ex instanceof PythonOrchestratorException pythonException) {
                throw pythonException;
            }
            throw new PythonOrchestratorException("Python Agent response parse failed, path=" + path, ex);
        }
    }

    private Request.Builder requestBuilder(String path) {
        Request.Builder builder = new Request.Builder()
                .url(agentBaseUrl.replaceAll("/$", "") + path)
                .addHeader("Accept", "application/json")
                .addHeader("X-MoodApp-Caller", "java-backend")
                .addHeader("X-Gateway-Request-Id", UUID.randomUUID().toString())
                .addHeader("X-Gateway-Timestamp", String.valueOf(System.currentTimeMillis()));

        if (gatewayToken != null && !gatewayToken.isBlank()) {
            builder.addHeader("X-Agent-Token", gatewayToken);
        }
        return builder;
    }

    JSONObject buildRequestBody(
            Long userId,
            String sessionId,
            String requestId,
            String message,
            List<PythonChatMessage> history,
            Map<String, Object> metadata
    ) {
        JSONObject body = new JSONObject();
        body.put("message", message);
        body.put("history", buildHistory(history));

        JSONObject context = new JSONObject();
        if (requestId != null && !requestId.isBlank()) {
            context.put("request_id", requestId);
        }
        if (userId != null) {
            context.put("user_id", userId);
        }
        if (sessionId != null && !sessionId.isBlank()) {
            context.put("session_id", sessionId);
        }
        if (metadata != null && !metadata.isEmpty()) {
            context.put("metadata", metadata);
        }
        body.put("context", context);
        return body;
    }

    private JSONArray buildHistory(List<PythonChatMessage> history) {
        JSONArray array = new JSONArray();
        if (history == null || history.isEmpty()) {
            return array;
        }

        List<PythonChatMessage> limited = new ArrayList<>(history);
        int fromIndex = Math.max(0, limited.size() - 12);
        for (PythonChatMessage item : limited.subList(fromIndex, limited.size())) {
            if (item == null || item.getRole() == null || item.getContent() == null) {
                continue;
            }
            String role = item.getRole();
            if (!"user".equals(role) && !"assistant".equals(role) && !"system".equals(role)) {
                continue;
            }
            if (item.getContent().isBlank()) {
                continue;
            }
            JSONObject msg = new JSONObject();
            msg.put("role", role);
            msg.put("content", item.getContent());
            array.add(msg);
        }
        return array;
    }

    public static class PythonOrchestratorException extends RuntimeException {
        public PythonOrchestratorException(String message) {
            super(message);
        }

        public PythonOrchestratorException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
