package com.example.app.entity;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@AllArgsConstructor
@NoArgsConstructor
@Data
public class InterventionPlan {

    private Long id;

    private Long userId;

    private Long parentPlanId;

    private Integer revisionNo;

    private String decisionSource;

    private String requestId;

    private String interventionLevel;

    private String riskLevelSource;

    private String strategy;

    private String actions;

    private String rationale;

    private Boolean requiresHumanReview;

    private String safetyConstraints;

    private String profileUsed;

    private String ragCitationsUsed;

    private Double confidence;

    private LocalDateTime createTime;
}
