package com.example.app.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@AllArgsConstructor
@NoArgsConstructor
public class RiskScoreResult {

    private Double emotionRisk;

    private Double trendRisk;

    private Double riskScore;
}
