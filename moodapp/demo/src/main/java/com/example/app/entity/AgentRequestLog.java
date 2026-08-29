package com.example.app.entity;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@AllArgsConstructor
@NoArgsConstructor
@Data
public class AgentRequestLog {

    private Long id;
    private Long userId;
    private String requestId;
    private String sessionId;
    private String messageHash;
    private String redactedMessageHash;
    private String agentEntry;
    private String workflowEngine;
    private String workflowVersion;
    private String modelName;
    private String status;
    private String errorCode;
    private Long latencyMs;
    private LocalDateTime createTime;
}
