package com.example.app.service.Impl;

import com.example.app.dto.MentalDTO;
import com.example.app.dto.RiskScoreResult;
import com.example.app.entity.MentalState;
import com.example.app.mapper.MentalStateMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

@Service
public class MultiSourceRiskAssessmentService {

    private static final int HISTORY_LIMIT = 5;

    @Autowired
    private MentalStateMapper mentalStateMapper;

    public RiskScoreResult calculate(Long userId, MentalDTO emotion) {
        if (userId == null) {
            throw new IllegalArgumentException("userId不能为空");
        }
        if (emotion == null) {
            throw new IllegalArgumentException("情绪分析结果不能为空");
        }

        double anxiety = normalizeScore(emotion.getAnxiety());
        double stress = normalizeScore(emotion.getStress());
        double depression = normalizeScore(emotion.getDepression());

        double emotionRisk = 0.4 * anxiety
                + 0.3 * stress
                + 0.3 * depression;

        List<MentalState> history =
                mentalStateMapper.findLatestHistory(userId, HISTORY_LIMIT);

        double trendRisk = calculateTrendRisk(stress, history);
        double riskScore = 0.7 * emotionRisk + 0.3 * trendRisk;

        return new RiskScoreResult(
                round(clamp(emotionRisk)),
                round(clamp(trendRisk)),
                round(clamp(riskScore))
        );
    }

    private double calculateTrendRisk(double currentStress, List<MentalState> history) {
        if (history == null || history.isEmpty()) {
            return 0.0;
        }

        double historicalAverageStress = history.stream()
                .map(MentalState::getStress)
                .filter(value -> value != null)
                .mapToDouble(this::normalizeScore)
                .average()
                .orElse(currentStress);

        return Math.max(0.0, currentStress - historicalAverageStress);
    }

    private double normalizeScore(Integer score) {
        if (score == null) {
            return 0.0;
        }
        return clamp(score.doubleValue());
    }

    private double clamp(double score) {
        return Math.max(0.0, Math.min(100.0, score));
    }

    private double round(double score) {
        return BigDecimal.valueOf(score)
                .setScale(2, RoundingMode.HALF_UP)
                .doubleValue();
    }
}
