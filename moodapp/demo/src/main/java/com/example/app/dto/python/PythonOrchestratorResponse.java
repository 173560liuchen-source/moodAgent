package com.example.app.dto.python;

import com.alibaba.fastjson.annotation.JSONField;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.util.List;
import java.util.Map;

@Data
public class PythonOrchestratorResponse {

    private String agent;

    @JSONField(name = "request_id")
    @JsonProperty("request_id")
    private String requestId;

    @JSONField(name = "session_id")
    @JsonProperty("session_id")
    private String sessionId;

    private Map<String, Object> safety;

    private String reply;

    private String model;

    private Map<String, Object> crisis;

    private Map<String, Object> emotion;

    private Map<String, Object> rag;

    private Map<String, Object> trend;

    private Map<String, Object> risk;

    private Map<String, Object> profile;

    private Map<String, Object> intervention;

    @JSONField(name = "follow_up")
    @JsonProperty("follow_up")
    private Map<String, Object> followUp;

    private Map<String, Object> evaluator;

    private Map<String, Object> audit;

    private Map<String, Object> persistence;

    private List<String> trace;

    @JSONField(name = "trace_events")
    @JsonProperty("trace_events")
    private List<Map<String, Object>> traceEvents;

    public boolean hasReply() {
        return reply != null && !reply.isBlank();
    }
}
