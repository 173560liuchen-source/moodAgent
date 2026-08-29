package com.example.app.entity;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@AllArgsConstructor
@NoArgsConstructor
@Data
public class PsychologicalTrend {

    private Long id;

    private String openId;

    private String anxietyTrend;

    private String stressTrend;

    private String emotionTrend;

    private String riskTrend;

    private String futureRisk;

    private String suggestions;

    private LocalDateTime createTime;
}