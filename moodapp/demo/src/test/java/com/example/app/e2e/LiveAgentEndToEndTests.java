package com.example.app.e2e;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONObject;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Real deployment acceptance test. It is deliberately opt-in because it writes
 * chat and analysis records. Point it only at a disposable test database.
 */
@Tag("e2e")
@EnabledIfEnvironmentVariable(named = "MOODAPP_E2E", matches = "true")
class LiveAgentEndToEndTests {

    @Test
    void chatToAgentWorkflowPersistsToTheLiveTestDatabase() throws Exception {
        String baseUrl = System.getenv().getOrDefault("MOODAPP_E2E_BASE_URL", "http://127.0.0.1:8080");
        String userId = requiredEnvironment("MOODAPP_E2E_USER_ID");
        String body = """
                {
                  "message":"我连续几天睡不好，学习压力很大，不知道该怎么办。",
                  "context":{"user_id":%s,"session_id":"e2e-live-session","request_id":"e2e-live-request","metadata":{"test_run":true}}
                }
                """.formatted(userId);

        HttpRequest request = HttpRequest.newBuilder(URI.create(baseUrl + "/agent/gateway/orchestrate"))
                .timeout(Duration.ofSeconds(90))
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();
        HttpResponse<String> response = HttpClient.newHttpClient()
                .send(request, HttpResponse.BodyHandlers.ofString());

        assertThat(response.statusCode()).isEqualTo(200);
        JSONObject root = JSON.parseObject(response.body());
        assertThat(root.getInteger("code")).isEqualTo(200);
        JSONObject data = root.getJSONObject("data");
        assertThat(data.getString("reply")).isNotBlank();
        assertThat(data.getJSONObject("persistence").getBoolean("chat_record_saved")).isTrue();
        assertThat(data.getJSONObject("persistence").getJSONArray("saved_steps")).isNotEmpty();
    }

    private String requiredEnvironment(String name) {
        String value = System.getenv(name);
        assertThat(value).as("Set %s to an existing user ID in the disposable E2E database", name).isNotBlank();
        return value;
    }
}
