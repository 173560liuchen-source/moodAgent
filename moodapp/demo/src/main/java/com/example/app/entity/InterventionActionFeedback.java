package com.example.app.entity;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class InterventionActionFeedback {
    private Long id;
    private Long userId;
    private Long planId;
    private String actionId;
    private String executionStatus;
    private String outcomeStatus;
    private Integer difficulty;
    private String feedbackNote;
    private String source;
    private LocalDateTime createTime;
}
