package com.example.app.service.Impl;

import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import com.example.app.dto.python.PythonChatMessage;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class PythonOrchestratorServiceContractTests {

    @Test
    void javaRequestPreservesHistoryRolesContentAndOrderAndPassesCrisisState() {
        PythonOrchestratorService service = new PythonOrchestratorService();
        List<PythonChatMessage> history = List.of(
                new PythonChatMessage("user", "我想好了计划"),
                new PythonChatMessage("assistant", "你是否拿到了工具？"),
                new PythonChatMessage("user", "有，在桌上")
        );
        Map<String, Object> crisisState = Map.of(
                "highest_recent_level", "high",
                "active_plan", true,
                "tool_access", true
        );

        JSONObject body = service.buildRequestBody(
                7L,
                "session-1",
                "request-1",
                "我没事",
                history,
                Map.of("crisis_state", crisisState)
        );

        JSONArray sentHistory = body.getJSONArray("history");
        assertThat(sentHistory).hasSize(3);
        assertThat(sentHistory.getJSONObject(0).getString("role")).isEqualTo("user");
        assertThat(sentHistory.getJSONObject(0).getString("content")).isEqualTo("我想好了计划");
        assertThat(sentHistory.getJSONObject(1).getString("role")).isEqualTo("assistant");
        assertThat(sentHistory.getJSONObject(2).getString("content")).isEqualTo("有，在桌上");
        assertThat(body.getJSONObject("context").getJSONObject("metadata")
                .getJSONObject("crisis_state").getString("highest_recent_level"))
                .isEqualTo("high");
    }
}
