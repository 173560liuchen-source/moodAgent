package com.example.app.entity;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class InterventionFollowUp {
    private Long id;
    private Long userId;
    private Long planId;
    private String requestId;
    private String adjustedPlanRequestId;
    private String feedbackText;
    private String adherence;
    private String effectiveness;
    private String decision;
    private String emotionChange;
    private String riskChange;
    private String evidence;
    private String adjustmentReason;
    private Double confidence;
    private LocalDateTime createTime;
}
