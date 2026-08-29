package com.example.app.entity;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@AllArgsConstructor
@NoArgsConstructor
@Data
public class AgentAuditEvent {

    private Long id;

    private Long userId;

    private String requestId;

    private String sessionId;

    private String agentTrace;

    private String traceEvents;

    private String safetyResult;

    private String crisisResult;

    private String emotionResult;

    private String ragResult;

    private String profileResult;

    private String interventionResult;

    private String evaluatorResult;

    private String auditResult;

    private String modelName;

    private String workflowEngine;

    private String workflowVersion;

    private Long latencyMs;

    private LocalDateTime createTime;
}
