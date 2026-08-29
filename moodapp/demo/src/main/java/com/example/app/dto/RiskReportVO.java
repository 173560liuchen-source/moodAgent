package com.example.app.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

@AllArgsConstructor
@NoArgsConstructor
@Data
public class RiskReportVO {

    private String riskLevel;

    private List<String> riskReasons;

    private List<String> dangerSignals;

    private List<String> suggestions;

    private String needCenter;

    private String conclusion;

    private String userFriendlyReport;

}