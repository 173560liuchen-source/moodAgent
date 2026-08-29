package com.example.app.entity;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@AllArgsConstructor
@NoArgsConstructor
@Data
public class ModelCallLog {

    private Long id;
    private Long userId;
    private String requestId;
    private String agentName;
    private String modelName;
    private String promptVersion;
    private Integer inputTokens;
    private Integer outputTokens;
    private Integer totalTokens;
    private Long latencyMs;
    private Boolean success;
    private String errorCode;
    private LocalDateTime createTime;
}
