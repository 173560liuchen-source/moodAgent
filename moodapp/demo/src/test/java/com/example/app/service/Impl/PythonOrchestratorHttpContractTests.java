package com.example.app.service.Impl;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONObject;
import com.example.app.dto.python.PythonChatMessage;
import com.example.app.dto.python.PythonOrchestratorResponse;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;

/** Verifies the wire contract used by Java when it calls the Python agent service. */
class PythonOrchestratorHttpContractTests {

    private HttpServer pythonStub;
    private final AtomicReference<HttpExchange> lastExchange = new AtomicReference<>();
    private final AtomicReference<String> lastBody = new AtomicReference<>("");
    private PythonOrchestratorService service;

    @BeforeEach
    void setUp() throws IOException {
        pythonStub = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        pythonStub.createContext("/", this::respondAsPythonAgent);
        pythonStub.start();
        service = new PythonOrchestratorService();
        ReflectionTestUtils.setField(service, "agentBaseUrl",
                "http://127.0.0.1:" + pythonStub.getAddress().getPort());
        ReflectionTestUtils.setField(service, "gatewayToken", "contract-test-token");
    }

    @AfterEach
    void tearDown() {
        pythonStub.stop(0);
    }

    @Test
    void javaCallsPythonWithExpectedHeadersPathsAndPayload() {
        PythonOrchestratorResponse result = service.orchestrate(
                42L, "session-contract", "request-contract", "我最近压力很大",
                List.of(new PythonChatMessage("user", "之前也睡不好")),
                Map.of("entrypoint", "contract-test")
        );

        assertThat(result.getReply()).isEqualTo("已收到你的消息");
        assertThat(lastExchange.get().getRequestURI().getPath()).isEqualTo("/v1/agents/orchestrate");
        assertThat(lastExchange.get().getRequestMethod()).isEqualTo("POST");
        assertThat(lastExchange.get().getRequestHeaders().getFirst("X-MoodApp-Caller")).isEqualTo("java-backend");
        assertThat(lastExchange.get().getRequestHeaders().getFirst("X-Agent-Token")).isEqualTo("contract-test-token");
        JSONObject payload = JSON.parseObject(lastBody.get());
        assertThat(payload.getString("message")).isEqualTo("我最近压力很大");
        assertThat(payload.getJSONArray("history").getJSONObject(0).getString("content")).isEqualTo("之前也睡不好");
        assertThat(payload.getJSONObject("context").getLong("user_id")).isEqualTo(42L);
        assertThat(payload.getJSONObject("context").getString("request_id")).isEqualTo("request-contract");
    }

    @Test
    void javaParsesPythonHealthAndRegistryContracts() {
        assertThat(service.health().getBoolean("ok")).isTrue();
        assertThat(lastExchange.get().getRequestURI().getPath()).isEqualTo("/health");
        assertThat(service.agentRegistry().getJSONArray("agents"))
                .extracting(item -> ((JSONObject) item).getString("name"))
                .contains("crisis", "rag");
        assertThat(lastExchange.get().getRequestURI().getPath()).isEqualTo("/v1/agents/registry");
    }

    private void respondAsPythonAgent(HttpExchange exchange) throws IOException {
        lastExchange.set(exchange);
        lastBody.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
        String path = exchange.getRequestURI().getPath();
        String body = switch (path) {
            case "/health" -> "{\"ok\":true,\"service\":\"python-agent\"}";
            case "/v1/agents/registry" -> "[{\"name\":\"crisis\"},{\"name\":\"rag\"}]";
            case "/v1/agents/orchestrate" -> "{\"request_id\":\"request-contract\",\"session_id\":\"session-contract\",\"reply\":\"已收到你的消息\",\"model\":\"contract-model\"}";
            default -> "{\"error\":\"unexpected path\"}";
        };
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().add("Content-Type", "application/json;charset=UTF-8");
        exchange.sendResponseHeaders(path.equals("/health") || path.startsWith("/v1/") ? 200 : 404, bytes.length);
        exchange.getResponseBody().write(bytes);
        exchange.close();
    }
}
