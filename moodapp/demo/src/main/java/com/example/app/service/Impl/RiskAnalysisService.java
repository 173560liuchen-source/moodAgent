package com.example.app.service.Impl;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import com.example.app.entity.ChatRecord;
import com.example.app.entity.MentalState;
import com.example.app.entity.RiskReport;
import com.example.app.mapper.ChatRecordMapper;
import com.example.app.mapper.MentalStateMapper;
import com.example.app.mapper.RiskReportMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.Collections;
import java.util.List;

@Service
public class RiskAnalysisService {

    private static final int RECENT_CHAT_LIMIT = 8;
    private static final int TREND_HISTORY_LIMIT = 30;

    @Autowired
    private ChatRecordMapper chatRecordMapper;

    @Autowired
    private MentalStateMapper mentalStateMapper;

    @Autowired
    private RiskReportMapper riskReportMapper;

    @Autowired
    private PythonOrchestratorService pythonOrchestratorService;

    public String analyzeRisk(Long userId) {
        return analyzeRiskWithPython(userId).toJSONString();
    }

    public RiskReport generateAndSaveRiskReport(Long userId) {
        JSONObject result = analyzeRiskWithPython(userId);
        RiskReport report = toRiskReport(userId, result);
        riskReportMapper.insert(report);
        return report;
    }

    private JSONObject analyzeRiskWithPython(Long userId) {
        if (userId == null) {
            throw new IllegalArgumentException("userId不能为空");
        }

        MentalState latest = mentalStateMapper.findLatestByUserId(userId);
        if (latest == null) {
            throw new IllegalStateException("未找到用户心理状态数据，无法生成风险报告");
        }

        List<ChatRecord> recentChats = chatRecordMapper.findRecentByUserId(userId, RECENT_CHAT_LIMIT);
        JSONObject crisis = buildCrisisInput(recentChats);
        JSONObject emotion = buildEmotionInput(latest, recentChats);
        JSONObject trend = buildTrendInput(userId);

        JSONObject result = pythonOrchestratorService.assessRisk(crisis, emotion, trend, null);
        System.out.println("[RiskAnalysisService] Python RiskAgent result=" + result.toJSONString());
        return result;
    }

    private JSONObject buildCrisisInput(List<ChatRecord> recentChats) {
        JSONArray evidence = new JSONArray();
        JSONArray ruleHits = new JSONArray();

        boolean selfHarm = false;
        boolean harmToOthers = false;
        boolean planPresent = false;
        boolean toolPresent = false;
        boolean timePresent = false;

        if (recentChats != null) {
            for (ChatRecord record : recentChats) {
                if (record == null || record.getContent() == null || !"user".equals(record.getRole())) {
                    continue;
                }
                String content = record.getContent();
                String shortText = shorten(content);

                if (containsAny(content, "自杀", "不想活", "结束生命", "伤害自己", "活着没意义", "不如死了")) {
                    selfHarm = true;
                    evidence.add(shortText);
                    ruleHits.add(ruleHit("java_self_harm_keyword", "self_harm_ideation", "medium", shortText));
                }
                if (containsAny(content, "杀了他", "伤害别人", "报复他们", "弄死", "打死")) {
                    harmToOthers = true;
                    evidence.add(shortText);
                    ruleHits.add(ruleHit("java_harm_to_others_keyword", "harm_to_others_ideation", "medium", shortText));
                }
                if (containsAny(content, "计划", "准备", "已经想好", "方法")) {
                    planPresent = true;
                }
                if (containsAny(content, "刀", "药", "绳", "楼顶", "煤气")) {
                    toolPresent = true;
                }
                if (containsAny(content, "今晚", "现在", "马上", "一会儿", "明天")) {
                    timePresent = true;
                }
            }
        }

        String level = "low";
        String action = "normal_support";
        String immediacy = "none";
        boolean requiresHuman = false;
        boolean hardRule = false;
        double confidence = 0.75;

        if ((selfHarm || harmToOthers) && (planPresent || toolPresent || timePresent)) {
            level = "high";
            action = "crisis_response";
            immediacy = timePresent ? "immediate" : "possible";
            requiresHuman = true;
            hardRule = true;
            confidence = 0.95;
        } else if (selfHarm || harmToOthers) {
            level = "medium";
            action = "check_in";
            immediacy = "possible";
            requiresHuman = true;
            confidence = 0.85;
        }

        JSONObject crisis = new JSONObject();
        crisis.put("level", level);
        crisis.put("self_harm", selfHarm);
        crisis.put("harm_to_others", harmToOthers);
        crisis.put("immediacy", immediacy);
        crisis.put("plan_present", planPresent);
        crisis.put("tool_present", toolPresent);
        crisis.put("time_present", timePresent);
        crisis.put("place_present", false);
        crisis.put("confidence", confidence);
        crisis.put("evidence", evidence);
        crisis.put("action", action);
        crisis.put("requires_human_review", requiresHuman);
        crisis.put("hard_rule_triggered", hardRule);
        crisis.put("rule_hits", ruleHits);
        crisis.put("decision_source", ruleHits.isEmpty() ? "model" : "rules");
        crisis.put("model_level", level);
        crisis.put("model_confidence", confidence);
        crisis.put("crisis_response", "由Java最近聊天记录规则扫描生成危机输入，再交给Python RiskAgent综合评估。");
        crisis.put("parse_status", "ok");
        crisis.put("prompt_version", "java-risk-input-1.0.0");
        crisis.put("validation_warnings", new JSONArray());
        return crisis;
    }

    private JSONObject buildEmotionInput(MentalState latest, List<ChatRecord> recentChats) {
        JSONArray evidence = new JSONArray();
        if (recentChats != null) {
            for (ChatRecord record : recentChats) {
                if (record != null && "user".equals(record.getRole()) && record.getContent() != null) {
                    evidence.add(shorten(record.getContent()));
                    if (evidence.size() >= 3) {
                        break;
                    }
                }
            }
        }

        JSONObject emotion = new JSONObject();
        emotion.put("emotion", inferEmotionLabel(latest));
        emotion.put("anxiety", toScore01(latest.getAnxiety()));
        emotion.put("stress", toScore01(latest.getStress()));
        emotion.put("depression", toScore01(latest.getDepression()));
        emotion.put("loneliness", 0.0);
        emotion.put("confidence", 0.75);
        emotion.put("evidence", evidence);
        emotion.put("insufficient_data", false);
        emotion.put("reason", "Java根据最新mental_state构造给Python RiskAgent的结构化情绪输入。");
        emotion.put("parse_status", "ok");
        emotion.put("prompt_version", "java-risk-input-1.0.0");
        emotion.put("validation_warnings", new JSONArray());
        return emotion;
    }

    private JSONObject buildTrendInput(Long userId) {
        List<MentalState> states = mentalStateMapper.findLatestHistory(userId, TREND_HISTORY_LIMIT);
        if (states == null || states.size() < 3) {
            return null;
        }

        Collections.reverse(states);
        JSONObject trend = pythonOrchestratorService.analyzeTrend(buildTrendPoints(states));
        trend.remove("agent");
        return trend;
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

    private RiskReport toRiskReport(Long userId, JSONObject result) {
        String riskLevel = result.getString("risk_level");
        Double riskScore = result.getDouble("risk_score");

        RiskReport report = new RiskReport();
        report.setUserId(userId);
        report.setRiskLevel(riskLevel == null ? "unknown" : riskLevel);
        report.setRiskReasons(toJsonArrayString(result.get("main_factors")));
        report.setDangerSignals(toJsonArrayString(result.get("evidence")));
        report.setSuggestions(toJsonArrayString(result.get("recommendation")));
        report.setNeedCenter(result.getBooleanValue("requires_human_review") ? "是" : "否");
        report.setConclusion("Python RiskAgent综合评估：当前风险等级为 "
                + report.getRiskLevel() + "，风险分=" + (riskScore == null ? "unknown" : riskScore));
        report.setUserFriendlyReport(truncate(result.toJSONString(), 1800));
        report.setCreateTime(LocalDateTime.now());
        return report;
    }

    private JSONObject ruleHit(String ruleId, String signalType, String severity, String evidence) {
        JSONObject hit = new JSONObject();
        hit.put("rule_id", ruleId);
        hit.put("signal_type", signalType);
        hit.put("severity", severity);
        hit.put("evidence", evidence);
        return hit;
    }

    private String inferEmotionLabel(MentalState latest) {
        double anxiety = toScore01(latest.getAnxiety());
        double stress = toScore01(latest.getStress());
        double depression = toScore01(latest.getDepression());
        if (stress >= anxiety && stress >= depression) {
            return "stressed";
        }
        if (anxiety >= depression) {
            return "anxious";
        }
        return "depressed";
    }

    private String toJsonArrayString(Object value) {
        if (value instanceof JSONArray) {
            return JSON.toJSONString(value);
        }
        JSONArray array = new JSONArray();
        if (value != null) {
            array.add(value);
        }
        return array.toJSONString();
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

    private boolean containsAny(String text, String... keywords) {
        if (text == null || keywords == null) {
            return false;
        }
        for (String keyword : keywords) {
            if (keyword != null && text.contains(keyword)) {
                return true;
            }
        }
        return false;
    }

    private String shorten(String text) {
        if (text == null) {
            return "";
        }
        return text.length() <= 120 ? text : text.substring(0, 120);
    }

    private String truncate(String value, int maxLength) {
        if (value == null) {
            return "";
        }
        return value.length() <= maxLength ? value : value.substring(0, maxLength);
    }
}
