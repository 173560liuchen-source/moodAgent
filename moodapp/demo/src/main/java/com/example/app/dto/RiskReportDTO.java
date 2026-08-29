package com.example.app.dto;

import lombok.Data;

import java.util.List;

@Data
public class RiskReportDTO {

    private String riskLevel;

    private List<String> riskReasons;

    private List<String> dangerSignals;

    private List<String> suggestions;

    private String needCenter;

    private String conclusion;

    private String userFriendlyReport;

}