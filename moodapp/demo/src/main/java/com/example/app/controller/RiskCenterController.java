package com.example.app.controller;

import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import com.example.app.dto.ApiResponse;
import com.example.app.entity.AgentAuditEvent;
import com.example.app.entity.MentalState;
import com.example.app.entity.RiskReport;
import com.example.app.entity.User;
import com.example.app.mapper.AgentAuditEventMapper;
import com.example.app.mapper.MentalStateMapper;
import com.example.app.mapper.RiskReportMapper;
import com.example.app.mapper.UserMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import jakarta.servlet.http.HttpServletRequest;
import com.example.app.utils.AuthenticatedUser;

@RestController
@RequestMapping("/agent/insights")
public class RiskCenterController {

    @Autowired
    private RiskReportMapper riskReportMapper;

    @Autowired
    private AgentAuditEventMapper agentAuditEventMapper;

    @Autowired
    private MentalStateMapper mentalStateMapper;

    @Autowired
    private UserMapper userMapper;

    @GetMapping("/risk-center")
    public ApiResponse<JSONObject> riskCenter(
            @RequestParam(required = false) Long userId,
            @RequestParam(required = false) String openid,
            @RequestParam(defaultValue = "30") int limit,
            HttpServletRequest request) {

        Long resolvedUserId = AuthenticatedUser.requireId(request);
        if (resolvedUserId == null) {
            return ApiResponse.error(404, "用户不存在");
        }

        int safeLimit = Math.max(1, Math.min(limit, 100));
        List<RiskReport> reports = riskReportMapper.findRecentByUserId(resolvedUserId, safeLimit);
        List<AgentAuditEvent> audits = agentAuditEventMapper.findRecentByUserId(resolvedUserId, safeLimit);
        List<MentalState> mentalStates = mentalStateMapper.findLatestHistory(resolvedUserId, safeLimit);
        List<JSONObject> events = buildEvents(reports, audits, mentalStates);

        if (events.isEmpty()) {
            events = buildAuditFallback(audits);
        }

        JSONObject result = new JSONObject();
        result.put("user_id", resolvedUserId);
        result.put("current", events.isEmpty() ? emptyCurrent() : events.get(0));
        result.put("events", events);
        result.put("trend", buildTrend(events));
        result.put("summary", buildSummary(events));
        return ApiResponse.success(result);
    }

    private Long resolveUserId(Long userId, String openid) {
        if (userId != null) {
            return userId;
        }
        if (openid == null || openid.isBlank()) {
            return null;
        }
        User user = userMapper.selectByOpenid(openid);
        return user == null ? null : user.getId();
    }

    private List<JSONObject> buildEvents(
            List<RiskReport> reports,
            List<AgentAuditEvent> audits,
            List<MentalState> mentalStates) {
        List<JSONObject> result = new ArrayList<>();
        for (RiskReport report : reports) {
            JSONObject reasons = asObject(parseJson(report.getRiskReasons()));
            JSONObject danger = asObject(parseJson(report.getDangerSignals()));
            JSONObject friendly = asObject(parseJson(report.getUserFriendlyReport()));
            JSONObject crisis = asObject(danger.get("crisis"));
            JSONObject risk = asObject(friendly.get("risk"));
            JSONObject emotion = asObject(friendly.get("emotion"));
            AgentAuditEvent audit = nearestAudit(report.getCreateTime(), audits);
            MentalState mentalState = nearestMentalState(report.getCreateTime(), mentalStates);

            JSONObject item = new JSONObject();
            item.put("id", report.getId());
            item.put("create_time", report.getCreateTime());
            item.put("risk_level", inferLevel(report.getRiskLevel(), report.getConclusion()));
            item.put("risk_score", firstNumber(
                    reasons.get("risk_score"),
                    risk.get("risk_score"),
                    mentalState == null ? null : mentalState.getRiskScore()));
            item.put("emotion_risk", firstNumber(
                    reasons.get("emotion_risk"),
                    risk.get("emotion_risk"),
                    mentalState == null ? null : mentalState.getEmotionRisk()));
            item.put("trend_risk", firstNumber(
                    reasons.get("trend_risk"),
                    risk.get("trend_risk"),
                    mentalState == null ? null : mentalState.getTrendRisk()));
            item.put("confidence", firstNumber(crisis.get("confidence"), risk.get("confidence")));
            item.put("main_factors", firstArray(reasons.get("main_factors"), risk.get("main_factors")));
            item.put("danger_signals", crisis.isEmpty() ? danger : crisis);
            item.put("safety_violations", danger.get("safety_violations"));
            item.put("suggestions", parseJson(report.getSuggestions()));
            item.put("conclusion", report.getConclusion());
            item.put("friendly_report", friendly);
            item.put("emotion", emotion);
            if (audit != null) {
                item.put("request_id", audit.getRequestId());
                item.put("session_id", audit.getSessionId());
                item.put("model_name", audit.getModelName());
                item.put("latency_ms", audit.getLatencyMs());
                item.put("agent_trace", parseJson(audit.getTraceEvents()));
                item.put("intervention", parseJson(audit.getInterventionResult()));
            }
            result.add(item);
        }
        return result;
    }

    private List<JSONObject> buildAuditFallback(List<AgentAuditEvent> audits) {
        List<JSONObject> result = new ArrayList<>();
        for (AgentAuditEvent audit : audits) {
            JSONObject crisis = asObject(parseJson(audit.getCrisisResult()));
            JSONObject emotion = asObject(parseJson(audit.getEmotionResult()));
            JSONObject item = new JSONObject();
            item.put("id", audit.getId());
            item.put("create_time", audit.getCreateTime());
            item.put("risk_level", normalizeLevel(crisis.getString("level")));
            item.put("risk_score", null);
            item.put("emotion_risk", null);
            item.put("trend_risk", null);
            item.put("confidence", crisis.getDouble("confidence"));
            item.put("main_factors", new JSONArray());
            item.put("danger_signals", crisis);
            item.put("suggestions", parseJson(audit.getInterventionResult()));
            item.put("conclusion", buildConclusion(crisis.getString("level")));
            item.put("emotion", emotion);
            item.put("request_id", audit.getRequestId());
            item.put("session_id", audit.getSessionId());
            item.put("model_name", audit.getModelName());
            item.put("latency_ms", audit.getLatencyMs());
            item.put("agent_trace", parseJson(audit.getTraceEvents()));
            item.put("intervention", parseJson(audit.getInterventionResult()));
            result.add(item);
        }
        return result;
    }

    private JSONObject buildSummary(List<JSONObject> events) {
        JSONObject summary = new JSONObject();
        int highCount = 0;
        int signalCount = 0;
        for (JSONObject event : events) {
            String level = event.getString("risk_level");
            if ("high".equals(level) || "critical".equals(level)) {
                highCount++;
            }
            signalCount += countSignals(event.getJSONObject("danger_signals"));
        }
        summary.put("event_count", events.size());
        summary.put("high_risk_count", highCount);
        summary.put("signal_count", signalCount);
        summary.put("highest_level", highestLevel(events));
        return summary;
    }

    private List<JSONObject> buildTrend(List<JSONObject> events) {
        List<JSONObject> trend = new ArrayList<>();
        for (JSONObject event : events) {
            JSONObject point = new JSONObject();
            point.put("time", event.get("create_time"));
            point.put("risk_level", event.getString("risk_level"));
            point.put("risk_score", event.get("risk_score"));
            point.put("emotion_risk", event.get("emotion_risk"));
            point.put("trend_risk", event.get("trend_risk"));
            trend.add(point);
        }
        Collections.reverse(trend);
        return trend;
    }

    private AgentAuditEvent nearestAudit(LocalDateTime reportTime, List<AgentAuditEvent> audits) {
        if (reportTime == null || audits == null || audits.isEmpty()) {
            return null;
        }
        AgentAuditEvent best = null;
        long bestDistance = Long.MAX_VALUE;
        for (AgentAuditEvent audit : audits) {
            if (audit.getCreateTime() == null) {
                continue;
            }
            long distance = Math.abs(Duration.between(reportTime, audit.getCreateTime()).toMillis());
            if (distance < bestDistance && distance <= 5 * 60 * 1000L) {
                best = audit;
                bestDistance = distance;
            }
        }
        return best;
    }

    private MentalState nearestMentalState(LocalDateTime reportTime, List<MentalState> mentalStates) {
        if (reportTime == null || mentalStates == null || mentalStates.isEmpty()) {
            return null;
        }
        MentalState best = null;
        long bestDistance = Long.MAX_VALUE;
        for (MentalState mentalState : mentalStates) {
            if (mentalState.getCreateTime() == null) {
                continue;
            }
            long distance = Math.abs(Duration.between(reportTime, mentalState.getCreateTime()).toMillis());
            if (distance < bestDistance && distance <= 30_000L) {
                best = mentalState;
                bestDistance = distance;
            }
        }
        return best;
    }

    private Object parseJson(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        try {
            return JSONObject.parse(raw);
        } catch (RuntimeException ex) {
            return raw;
        }
    }

    private JSONObject asObject(Object value) {
        return value instanceof JSONObject object ? object : new JSONObject();
    }

    private JSONArray firstArray(Object... values) {
        for (Object value : values) {
            if (value instanceof JSONArray array) {
                return array;
            }
            if (value instanceof List<?> list) {
                return new JSONArray(list);
            }
            if (value instanceof String text && !text.isBlank()) {
                JSONArray array = new JSONArray();
                array.add(text);
                return array;
            }
        }
        return new JSONArray();
    }

    private Double firstNumber(Object... values) {
        for (Object value : values) {
            if (value instanceof Number number) {
                return number.doubleValue();
            }
            if (value != null) {
                try {
                    return Double.parseDouble(String.valueOf(value));
                } catch (NumberFormatException ignored) {
                }
            }
        }
        return null;
    }

    private String normalizeLevel(String raw) {
        String level = raw == null ? "unknown" : raw.trim().toLowerCase();
        return switch (level) {
            case "medium", "attention" -> "attention";
            case "high", "critical", "low" -> level;
            default -> "unknown";
        };
    }

    private String inferLevel(String raw, String conclusion) {
        String normalized = normalizeLevel(raw);
        if (!"unknown".equals(normalized)) {
            return normalized;
        }
        String text = conclusion == null ? "" : conclusion.toLowerCase();
        if (text.contains("紧急风险") || text.contains("critical")) {
            return "critical";
        }
        if (text.contains("高风险") || text.contains("high risk")) {
            return "high";
        }
        if (text.contains("中风险") || text.contains("中等风险")
                || text.contains("需要关注") || text.contains("medium")) {
            return "attention";
        }
        if (text.contains("低风险") || text.contains("low risk")) {
            return "low";
        }
        return "unknown";
    }

    private int countSignals(JSONObject signals) {
        if (signals == null) {
            return 0;
        }
        int count = 0;
        for (String key : List.of("self_harm", "harm_to_others", "plan_present", "tool_present",
                "time_present", "place_present", "hard_rule_triggered")) {
            if (Boolean.TRUE.equals(signals.getBoolean(key))) {
                count++;
            }
        }
        return count;
    }

    private String highestLevel(List<JSONObject> events) {
        String highest = "unknown";
        int highestRank = -1;
        for (JSONObject event : events) {
            String level = event.getString("risk_level");
            int rank = switch (level == null ? "unknown" : level) {
                case "critical" -> 4;
                case "high" -> 3;
                case "attention" -> 2;
                case "low" -> 1;
                default -> 0;
            };
            if (rank > highestRank) {
                highest = level;
                highestRank = rank;
            }
        }
        return highest;
    }

    private JSONObject emptyCurrent() {
        JSONObject current = new JSONObject();
        current.put("risk_level", "unknown");
        current.put("main_factors", new JSONArray());
        current.put("danger_signals", new JSONObject());
        current.put("suggestions", new JSONArray());
        current.put("conclusion", "暂无风险识别数据");
        return current;
    }

    private String buildConclusion(String level) {
        return "当前自动风险识别结果为：" + normalizeLevel(level);
    }
}
