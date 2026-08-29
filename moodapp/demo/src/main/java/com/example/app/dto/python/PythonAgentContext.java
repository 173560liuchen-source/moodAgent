package com.example.app.dto.python;

import com.alibaba.fastjson.annotation.JSONField;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.HashMap;
import java.util.Map;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class PythonAgentContext {

    @JSONField(name = "request_id")
    @JsonProperty("request_id")
    private String requestId;

    @JSONField(name = "user_id")
    @JsonProperty("user_id")
    private Long userId;

    @JSONField(name = "session_id")
    @JsonProperty("session_id")
    private String sessionId;

    private Map<String, Object> metadata = new HashMap<>();
}
