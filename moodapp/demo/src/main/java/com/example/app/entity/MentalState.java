package com.example.app.entity;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Data
@AllArgsConstructor
@NoArgsConstructor
public class MentalState {
    private Long userId;
    private Integer anxiety;
    private Integer stress;
    private Integer depression;
    private Double emotionRisk;
    private Double trendRisk;
    private Double riskScore;
    private LocalDateTime createTime;
}
