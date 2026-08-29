package com.example.app.service.Impl;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import com.example.app.entity.MentalState;
import com.example.app.entity.PsychologicalTrend;
import com.example.app.entity.User;
import com.example.app.mapper.MentalStateMapper;
import com.example.app.mapper.TrendMapper;
import com.example.app.mapper.UserMapper;
import com.example.app.service.TrendService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.Collections;
import java.util.List;

@Service
public class TrendServiceImpl implements TrendService {

    private static final int HISTORY_LIMIT = 30;
    private static final int MIN_POINTS = 3;

    @Autowired
    private TrendMapper trendMapper;

    @Autowired
    private UserMapper userMapper;

    @Autowired
    private MentalStateMapper mentalStateMapper;

    @Autowired
    private PythonOrchestratorService pythonOrchestratorService;

    @Override
    public void generateTrend(String openId) {
        if (openId == null || openId.isBlank()) {
            throw new IllegalArgumentException("openId不能为空");
        }

        User user = userMapper.selectByOpenid(openId);
        if (user == null) {
            throw new IllegalArgumentException("用户不存在");
        }

        List<MentalState> states = mentalStateMapper.findLatestHistory(user.getId(), HISTORY_LIMIT);
        if (states == null || states.size() < MIN_POINTS) {
            throw new IllegalStateException("心理状态数据不足，至少需要3条记录才能生成趋势");
        }

        Collections.reverse(states);
        JSONObject result = pythonOrchestratorService.analyzeTrend(buildTrendPoints(states));

        PsychologicalTrend trend = new PsychologicalTrend();
        trend.setOpenId(openId);
        trend.setAnxietyTrend(result.getString("anxiety_trend"));
        trend.setStressTrend(result.getString("stress_trend"));
        trend.setEmotionTrend(buildEmotionTrendSummary(result));
        trend.setRiskTrend(buildRiskTrendSummary(result));
        trend.setFutureRisk(buildFutureRiskSummary(result));
        trend.setSuggestions(truncate(JSON.toJSONString(result), 1800));
        trend.setCreateTime(LocalDateTime.now());

        trendMapper.insert(trend);
        System.out.println("[TrendService] Python TrendAgent result saved, openId=" + openId
                + ", dataPoints=" + result.getInteger("data_points")
                + ", stressTrend=" + result.getString("stress_trend"));
    }

    @Override
    public Object findLatest(String openId) {
        return trendMapper.findLatest(openId);
    }

    private JSONArray buildTrendPoints(List<MentalState> states) {
        JSONArray points = new JSONArray();
        for (MentalState state : states) {
            JSONObject point = new JSONObject();
            point.put("timestamp", toIsoTimestamp(state.getCreateTime()));
            point.put("anxiety", toScore01(state.getAnxiety()));
            point.put("stress", toScore01(state.getStress()));
            point.put("depression", toScore01(state.getDepression()));
            point.put("intervention", false);
            point.put("intervention_type", null);
            points.add(point);
        }
        return points;
    }

    private String buildEmotionTrendSummary(JSONObject result) {
        JSONObject summary = new JSONObject();
        summary.put("stress_average", result.getDouble("stress_average"));
        summary.put("stress_delta", result.getDouble("stress_delta"));
        summary.put("consecutive_rise", result.getInteger("consecutive_rise"));
        summary.put("confidence", result.getDouble("confidence"));
        summary.put("window_7d", result.get("window_7d"));
        summary.put("window_30d", result.get("window_30d"));
        return truncate(summary.toJSONString(), 1800);
    }

    private String buildRiskTrendSummary(JSONObject result) {
        JSONObject summary = new JSONObject();
        summary.put("depression_trend", result.getString("depression_trend"));
        summary.put("recurrence", result.get("recurrence"));
        summary.put("calculation_trace", result.get("calculation_trace"));
        summary.put("evidence", result.get("evidence"));
        return truncate(summary.toJSONString(), 1800);
    }

    private String buildFutureRiskSummary(JSONObject result) {
        JSONObject summary = new JSONObject();
        summary.put("recurrence", result.get("recurrence"));
        summary.put("intervention_comparison", result.get("intervention_comparison"));
        summary.put("insufficient_reasons", result.get("insufficient_reasons"));
        return truncate(summary.toJSONString(), 1800);
    }

    private String toIsoTimestamp(LocalDateTime time) {
        LocalDateTime safeTime = time == null ? LocalDateTime.now() : time;
        return safeTime.atOffset(ZoneOffset.ofHours(8)).toInstant().toString();
    }

    private double toScore01(Number value) {
        if (value == null) {
            return 0.0;
        }
        double number = value.doubleValue();
        if (number > 1.0) {
            number = number / 100.0;
        }
        return Math.max(0.0, Math.min(1.0, Math.round(number * 10000.0) / 10000.0));
    }

    private String truncate(String value, int maxLength) {
        if (value == null) {
            return "";
        }
        return value.length() <= maxLength ? value : value.substring(0, maxLength);
    }
}
