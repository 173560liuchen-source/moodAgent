package com.example.app.service.Impl;

import com.alibaba.fastjson.JSONObject;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

@Service
public class PythonSafetyGateService {

    private static final MediaType JSON = MediaType.parse("application/json; charset=utf-8");

    private final OkHttpClient client = new OkHttpClient.Builder()
            .connectTimeout(3, TimeUnit.SECONDS)
            .readTimeout(5, TimeUnit.SECONDS)
            .writeTimeout(3, TimeUnit.SECONDS)
            .build();

    @Value("${moodapp.agent.base-url:http://127.0.0.1:8081}")
    private String agentBaseUrl;

    public String sanitize(String content) {
        JSONObject result = callSafetyGate(content);
        String decision = result.getString("decision");
        if ("block".equals(decision) || "escalate".equals(decision)) {
            throw new SafetyGateException("Message rejected by SafetyGate");
        }
        return readRedactedMessage(result);
    }

    public String sanitizeForOrchestrator(String content) {
        JSONObject result = callSafetyGate(content);
        String decision = result.getString("decision");
        if ("block".equals(decision)) {
            throw new SafetyGateException("Message blocked by SafetyGate");
        }
        return readRedactedMessage(result);
    }

    private JSONObject callSafetyGate(String content) {
        JSONObject body = new JSONObject();
        body.put("message", content);

        Request request = new Request.Builder()
                .url(agentBaseUrl.replaceAll("/$", "") + "/v1/agents/safety")
                .post(RequestBody.create(body.toJSONString(), JSON))
                .build();

        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful() || response.body() == null) {
                throw new SafetyGateException("SafetyGate unavailable");
            }

            JSONObject result = JSONObject.parseObject(response.body().string());
            return result;
        } catch (IOException | RuntimeException ex) {
            if (ex instanceof SafetyGateException safetyGateException) {
                throw safetyGateException;
            }
            throw new SafetyGateException("SafetyGate request failed", ex);
        }
    }

    private String readRedactedMessage(JSONObject result) {
        String redacted = result.getString("redacted_message");
        if (redacted == null || redacted.isBlank()) {
            throw new SafetyGateException("SafetyGate returned empty content");
        }
        return redacted;
    }

    public static class SafetyGateException extends RuntimeException {
        public SafetyGateException(String message) {
            super(message);
        }

        public SafetyGateException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
