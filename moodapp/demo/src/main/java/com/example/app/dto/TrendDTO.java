package com.example.app.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@AllArgsConstructor
@NoArgsConstructor
@Data
public class TrendDTO {

    private String anxietyTrend;

    private String stressTrend;

    private String emotionTrend;

    private String riskTrend;

    private String futureRisk;

    private String suggestions;
}