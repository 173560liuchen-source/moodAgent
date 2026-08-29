package com.example.app.entity;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@AllArgsConstructor
@NoArgsConstructor
@Data
public class CrisisEventLog {

    private Long id;
    private Long userId;
    private String requestId;
    private String level;
    private Boolean selfHarm;
    private Boolean harmToOthers;
    private String immediacy;
    private Boolean planPresent;
    private Boolean toolPresent;
    private Boolean timePresent;
    private Boolean placePresent;
    private Double confidence;
    private String evidence;
    private String action;
    private Boolean requiresHumanReview;
    private Boolean hardRuleTriggered;
    private String ruleHits;
    private String decisionSource;
    private LocalDateTime createTime;
}
