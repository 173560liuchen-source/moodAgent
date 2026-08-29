package com.example.app.entity;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@AllArgsConstructor
@NoArgsConstructor
@Data
public class RiskReport {

    private Long id;

    private Long userId;

    private String riskLevel;

    private String riskReasons;

    private String dangerSignals;

    private String suggestions;

    private String needCenter;

    private String conclusion;

    private String userFriendlyReport;

    private LocalDateTime createTime;

}