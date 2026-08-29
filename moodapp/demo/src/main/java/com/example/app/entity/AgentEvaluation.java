package com.example.app.entity;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@AllArgsConstructor
@NoArgsConstructor
@Data
public class AgentEvaluation {

    private Long id;

    private Long userId;

    private String requestId;

    private Boolean passed;

    private Double score;

    private String action;

    private String issues;

    private String checkedDimensions;

    private String correctedReply;

    private String finalReply;

    private Boolean requiresHumanReview;

    private Double ragGroundingScore;

    private LocalDateTime createTime;
}
