package com.example.app.controller;

import com.alibaba.fastjson.JSONObject;
import com.example.app.dto.ApiResponse;
import com.example.app.entity.AgentAuditEvent;
import com.example.app.entity.ChatRecord;
import com.example.app.entity.InterventionActionFeedback;
import com.example.app.entity.InterventionPlan;
import com.example.app.entity.ProfileItem;
import com.example.app.entity.PsychologicalProfile;
import com.example.app.entity.User;
import com.example.app.mapper.AgentAuditEventMapper;
import com.example.app.mapper.AgentEvaluationMapper;
import com.example.app.mapper.InterventionPlanMapper;
import com.example.app.mapper.InterventionActionFeedbackMapper;
import com.example.app.mapper.InterventionFollowUpMapper;
import com.example.app.mapper.ProfileItemMapper;
import com.example.app.mapper.ProfileMapper;
import com.example.app.mapper.UserMapper;
import com.example.app.service.ChatRecordService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import com.example.app.utils.AuthenticatedUser;

@RestController
@RequestMapping("/agent/insights")
public class AgentInsightController {

    @Autowired
    private UserMapper userMapper;

    @Autowired
    private ProfileItemMapper profileItemMapper;

    @Autowired
    private ProfileMapper profileMapper;

    @Autowired
    private InterventionPlanMapper interventionPlanMapper;

    @Autowired
    private InterventionFollowUpMapper interventionFollowUpMapper;

    @Autowired
    private InterventionActionFeedbackMapper interventionActionFeedbackMapper;

    @Autowired
    private AgentEvaluationMapper agentEvaluationMapper;

    @Autowired
    private AgentAuditEventMapper agentAuditEventMapper;

    @Autowired
    private ChatRecordService chatRecordService;

    @GetMapping("/latest")
    public ApiResponse<JSONObject> latest(@RequestParam(required = false) String openid, HttpServletRequest request) {
        User user = userMapper.selectById(AuthenticatedUser.requireId(request));
        if (user == null) {
            return ApiResponse.error("用户不存在");
        }

        JSONObject result = new JSONObject();
        result.put("user_id", user.getId());
        result.put("profile_items", profileItemMapper.findEnabledByUserId(user.getId()));
        result.put("latest_intervention", interventionPlanMapper.findLatestByUserId(user.getId()));
        result.put("latest_evaluation", agentEvaluationMapper.findLatestByUserId(user.getId()));
        result.put("recent_audit_events", agentAuditEventMapper.findRecentByUserId(user.getId(), 30));
        return ApiResponse.success(result);
    }

    @GetMapping("/session-center")
    public ApiResponse<JSONObject> sessionCenter(
            @RequestParam(required = false) Long userId,
            @RequestParam(required = false) String openid,
            @RequestParam(defaultValue = "8") int limit,
            HttpServletRequest request) {

        Long resolvedUserId = AuthenticatedUser.requireId(request);
        if (resolvedUserId == null) {
            return ApiResponse.error("user not found");
        }

        int safeLimit = Math.max(1, Math.min(limit, 20));
        List<AgentAuditEvent> auditEvents = agentAuditEventMapper.findRecentByUserId(resolvedUserId, 30);
        List<Map<String, Object>> grouped = chatRecordService.getRecordsGrouped(resolvedUserId, safeLimit);
        List<JSONObject> sessions = buildSessions(grouped, auditEvents);

        JSONObject result = new JSONObject();
        result.put("user_id", resolvedUserId);
        result.put("sessions", sessions);
        result.put("current_session", sessions.isEmpty() ? null : sessions.get(sessions.size() - 1));
        result.put("status", buildStatus(sessions, resolvedUserId));
        result.put("profile_items", profileItemMapper.findEnabledByUserId(resolvedUserId));
        result.put("latest_intervention", interventionPlanMapper.findLatestByUserId(resolvedUserId));
        result.put("recent_intervention_follow_ups", interventionFollowUpMapper.findRecentByUserId(resolvedUserId, safeLimit));
        result.put("recent_intervention_action_feedbacks", interventionActionFeedbackMapper.findRecentByUserId(resolvedUserId, 100));
        result.put("latest_evaluation", agentEvaluationMapper.findLatestByUserId(resolvedUserId));
        result.put("recent_audit_events", auditEvents);
        return ApiResponse.success(result);
    }

    @PostMapping("/intervention-feedback")
    public ApiResponse<JSONObject> submitInterventionFeedback(
            @RequestParam(required = false) Long userId,
            @RequestBody Map<String, Object> body,
            HttpServletRequest request) {
        userId = AuthenticatedUser.requireId(request);
        if (userId == null || body == null) {
            return ApiResponse.error(400, "userId 和反馈内容不能为空");
        }
        Long planId;
        try {
            planId = Long.valueOf(String.valueOf(body.get("planId")));
        } catch (Exception ex) {
            return ApiResponse.error(400, "planId 格式不正确");
        }
        InterventionPlan plan = interventionPlanMapper.findByIdAndUserId(planId, userId);
        if (plan == null) {
            return ApiResponse.error(404, "干预方案不存在或无权反馈");
        }

        String actionId = text(body.get("actionId"));
        String executionStatus = text(body.get("executionStatus"));
        String outcomeStatus = text(body.get("outcomeStatus"));
        if (actionId.isBlank() || !List.of("completed", "partial", "not_started").contains(executionStatus)
                || !List.of("improved", "unchanged", "worsened", "unknown").contains(outcomeStatus)) {
            return ApiResponse.error(400, "反馈状态不合法");
        }

        Integer difficulty = null;
        if (body.get("difficulty") != null && !String.valueOf(body.get("difficulty")).isBlank()) {
            try {
                difficulty = Integer.valueOf(String.valueOf(body.get("difficulty")));
            } catch (NumberFormatException ex) {
                return ApiResponse.error(400, "难度必须是 1 到 5 的整数");
            }
            if (difficulty < 1 || difficulty > 5) {
                return ApiResponse.error(400, "难度必须是 1 到 5 的整数");
            }
        }

        InterventionActionFeedback feedback = new InterventionActionFeedback();
        feedback.setUserId(userId);
        feedback.setPlanId(planId);
        feedback.setActionId(actionId);
        feedback.setExecutionStatus(executionStatus);
        feedback.setOutcomeStatus(outcomeStatus);
        feedback.setDifficulty(difficulty);
        feedback.setFeedbackNote(truncate(text(body.get("feedbackNote")), 500));
        feedback.setSource("page");
        feedback.setCreateTime(LocalDateTime.now());
        interventionActionFeedbackMapper.insert(feedback);

        JSONObject result = new JSONObject();
        result.put("saved", true);
        result.put("plan_id", planId);
        result.put("action_id", actionId);
        return ApiResponse.success(result);
    }

    @PutMapping("/profile-item")
    public ApiResponse<JSONObject> updateProfileItem(@RequestParam(required = false) Long userId, @RequestBody Map<String, Object> body, HttpServletRequest request) {
        userId = AuthenticatedUser.requireId(request);
        if (userId == null || body == null || body.get("id") == null) {
            return ApiResponse.error(400, "userId 和 id 不能为空");
        }

        Long itemId = Long.valueOf(String.valueOf(body.get("id")));
        String value = String.valueOf(body.getOrDefault("value", "")).trim();
        String evidence = String.valueOf(body.getOrDefault("evidence", "")).trim();
        if (value.isBlank()) {
            return ApiResponse.error(400, "画像内容不能为空");
        }

        int updated = profileItemMapper.updateEditableItem(itemId, userId, value, evidence);
        if (updated <= 0) {
            return ApiResponse.error(404, "画像项不存在或不可修改");
        }

        JSONObject result = new JSONObject();
        result.put("id", itemId);
        result.put("updated", true);
        return ApiResponse.success(result);
    }

    @GetMapping("/profile-center")
    public ApiResponse<JSONObject> profileCenter(
            @RequestParam(required = false) Long userId,
            @RequestParam(required = false) String openid,
            HttpServletRequest request) {

        Long resolvedUserId = AuthenticatedUser.requireId(request);
        if (resolvedUserId == null) {
            return ApiResponse.error(404, "用户不存在");
        }

        List<ProfileItem> items = profileItemMapper.findEnabledByUserId(resolvedUserId);
        PsychologicalProfile profile = profileMapper.findLatest(resolvedUserId);

        long sensitiveCount = items.stream()
                .filter(item -> "sensitive".equalsIgnoreCase(item.getSensitivity()))
                .count();
        long categoryCount = items.stream()
                .map(ProfileItem::getCategory)
                .filter(category -> category != null && !category.isBlank())
                .distinct()
                .count();
        double averageConfidence = items.stream()
                .map(ProfileItem::getConfidence)
                .filter(confidence -> confidence != null)
                .mapToDouble(Double::doubleValue)
                .average()
                .orElse(0.0);
        LocalDateTime lastUpdated = items.stream()
                .map(item -> item.getUpdateTime() != null ? item.getUpdateTime() : item.getCreateTime())
                .filter(time -> time != null)
                .max(LocalDateTime::compareTo)
                .orElse(profile == null ? null : profile.getCreateTime());

        JSONObject metrics = new JSONObject();
        metrics.put("item_count", items.size());
        metrics.put("category_count", categoryCount);
        metrics.put("average_confidence", Math.round(averageConfidence * 1000.0) / 10.0);
        metrics.put("sensitive_count", sensitiveCount);
        metrics.put("last_updated", lastUpdated);

        JSONObject result = new JSONObject();
        result.put("user_id", resolvedUserId);
        result.put("profile", profile);
        result.put("profile_items", items);
        result.put("profile_traits", buildProfileTraits(items));
        result.put("metrics", metrics);
        return ApiResponse.success(result);
    }

    private List<JSONObject> buildProfileTraits(List<ProfileItem> items) {
        Map<String, List<ProfileItem>> grouped = new LinkedHashMap<>();
        for (ProfileItem item : items) {
            String category = item.getCategory() == null || item.getCategory().isBlank()
                    ? "other"
                    : item.getCategory();
            grouped.computeIfAbsent(category, key -> new ArrayList<>()).add(item);
        }

        List<JSONObject> traits = new ArrayList<>();
        for (Map.Entry<String, List<ProfileItem>> entry : grouped.entrySet()) {
            List<String> values = new ArrayList<>();
            List<String> sources = new ArrayList<>();
            List<String> evidences = new ArrayList<>();
            Map<String, Double> uniqueConfidence = new LinkedHashMap<>();
            LocalDateTime latest = null;
            int sensitiveCount = 0;

            for (ProfileItem item : entry.getValue()) {
                String value = item.getValue() == null ? "" : item.getValue().trim();
                if (!value.isBlank() && !values.contains(value)) {
                    values.add(value);
                }
                if (!value.isBlank() && item.getConfidence() != null) {
                    uniqueConfidence.merge(value, item.getConfidence(), Math::max);
                }
                String source = item.getSource() == null ? "" : item.getSource().trim();
                if (!source.isBlank() && !sources.contains(source)) {
                    sources.add(source);
                }
                String evidence = item.getEvidence() == null ? "" : item.getEvidence().trim();
                if (!evidence.isBlank() && !evidences.contains(evidence)) {
                    evidences.add(evidence);
                }
                if ("sensitive".equalsIgnoreCase(item.getSensitivity())) {
                    sensitiveCount++;
                }
                LocalDateTime itemTime = item.getUpdateTime() != null ? item.getUpdateTime() : item.getCreateTime();
                if (itemTime != null && (latest == null || itemTime.isAfter(latest))) {
                    latest = itemTime;
                }
            }

            double averageConfidence = uniqueConfidence.values().stream()
                    .mapToDouble(Double::doubleValue)
                    .average()
                    .orElse(0.0);

            JSONObject trait = new JSONObject();
            trait.put("category", entry.getKey());
            trait.put("values", values);
            trait.put("sources", sources);
            trait.put("evidences", evidences);
            trait.put("item_count", entry.getValue().size());
            trait.put("unique_value_count", values.size());
            trait.put("sensitive_count", sensitiveCount);
            trait.put("average_confidence", Math.round(averageConfidence * 1000.0) / 1000.0);
            trait.put("last_updated", latest);
            traits.add(trait);
        }
        return traits;
    }

    @DeleteMapping("/profile-item")
    public ApiResponse<JSONObject> deleteProfileItem(@RequestParam(required = false) Long userId, @RequestParam Long id, HttpServletRequest request) {
        userId = AuthenticatedUser.requireId(request);
        if (userId == null || id == null) {
            return ApiResponse.error(400, "userId 和 id 不能为空");
        }

        int deleted = profileItemMapper.softDeleteItem(id, userId);
        if (deleted <= 0) {
            return ApiResponse.error(404, "画像项不存在或不可删除");
        }

        JSONObject result = new JSONObject();
        result.put("id", id);
        result.put("deleted", true);
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

    private String text(Object value) {
        return value == null ? "" : String.valueOf(value).trim();
    }

    private String truncate(String value, int maxLength) {
        return value.length() <= maxLength ? value : value.substring(0, maxLength);
    }

    private List<JSONObject> buildSessions(List<Map<String, Object>> grouped, List<AgentAuditEvent> auditEvents) {
        List<JSONObject> sessions = new ArrayList<>();
        for (int i = 0; i < grouped.size(); i++) {
            Map<String, Object> raw = grouped.get(i);
            List<ChatRecord> records = (List<ChatRecord>) raw.getOrDefault("messages", List.of());
            AgentAuditEvent matchedAudit = findAuditForSession(records, auditEvents);
            JSONObject analysis = buildAnalysis(matchedAudit);
            JSONObject session = new JSONObject();
            session.put("session_id", resolveSessionId(records, i));
            session.put("time", raw.get("time"));
            session.put("day_label", buildDayLabel(raw.get("time")));
            session.put("message_count", records.size());
            session.put("title", buildTitle(records));
            session.put("preview", buildPreview(records));
            session.put("emotion_label", inferEmotionLabel(records, analysis));
            session.put("risk_label", inferRiskLabel(analysis));
            session.put("messages", buildMessages(records));
            session.put("analysis_status", matchedAudit == null ? "missing" : "matched");
            session.put("analysis", analysis);
            sessions.add(session);
        }
        return sessions;
    }

    private AgentAuditEvent findAuditForSession(List<ChatRecord> records, List<AgentAuditEvent> auditEvents) {
        if (records == null || records.isEmpty() || auditEvents == null || auditEvents.isEmpty()) {
            return null;
        }

        for (int index = records.size() - 1; index >= 0; index--) {
            String requestId = records.get(index).getRequestId();
            if (requestId == null || requestId.isBlank()) {
                continue;
            }
            for (AgentAuditEvent event : auditEvents) {
                if (requestId.equals(event.getRequestId())) {
                    return event;
                }
            }
        }

        // 兼容迁移前的历史记录：仅用于会话摘要，前端不会再把它当作每一轮的精确链路。
        LocalDateTime start = records.stream()
                .map(ChatRecord::getCreateTime)
                .filter(time -> time != null)
                .min(LocalDateTime::compareTo)
                .orElse(null);
        LocalDateTime end = records.stream()
                .map(ChatRecord::getCreateTime)
                .filter(time -> time != null)
                .max(LocalDateTime::compareTo)
                .orElse(null);

        if (start == null || end == null) {
            return null;
        }

        LocalDateTime lowerBound = start.minusSeconds(30);
        LocalDateTime upperBound = end.plusMinutes(3);
        AgentAuditEvent best = null;
        long bestDistance = Long.MAX_VALUE;

        for (AgentAuditEvent event : auditEvents) {
            LocalDateTime eventTime = event.getCreateTime();
            if (eventTime == null || eventTime.isBefore(lowerBound) || eventTime.isAfter(upperBound)) {
                continue;
            }
            long distance = Math.abs(java.time.Duration.between(end, eventTime).toMillis());
            if (distance < bestDistance) {
                best = event;
                bestDistance = distance;
            }
        }
        return best;
    }

    private String resolveSessionId(List<ChatRecord> records, int index) {
        for (ChatRecord record : records) {
            if (record.getSessionId() != null && !record.getSessionId().isBlank()) {
                return record.getSessionId();
            }
        }
        return "legacy-session-" + (index + 1);
    }

    private JSONObject buildAnalysis(AgentAuditEvent audit) {
        JSONObject analysis = new JSONObject();
        if (audit == null) {
            analysis.put("matched", false);
            return analysis;
        }

        analysis.put("matched", true);
        analysis.put("request_id", audit.getRequestId());
        analysis.put("session_id", audit.getSessionId());
        analysis.put("model_name", audit.getModelName());
        analysis.put("workflow_engine", audit.getWorkflowEngine());
        analysis.put("workflow_version", audit.getWorkflowVersion());
        analysis.put("latency_ms", audit.getLatencyMs());
        analysis.put("create_time", audit.getCreateTime());
        analysis.put("agent_trace", parseJson(audit.getAgentTrace()));
        analysis.put("trace_events", parseJson(audit.getTraceEvents()));
        JSONObject auditResult = parseJsonObject(audit.getAuditResult());
        JSONObject traceSummary = auditResult == null ? null : auditResult.getJSONObject("trace_summary");
        analysis.put("route", traceSummary == null ? null : traceSummary.getString("route"));
        analysis.put("routing", auditResult == null ? null : auditResult.getJSONObject("routing"));
        analysis.put("safety", parseJson(audit.getSafetyResult()));
        analysis.put("crisis", parseJson(audit.getCrisisResult()));
        analysis.put("emotion", parseJson(audit.getEmotionResult()));
        analysis.put("rag", parseJson(audit.getRagResult()));
        analysis.put("profile", parseJson(audit.getProfileResult()));
        analysis.put("intervention", parseJson(audit.getInterventionResult()));
        analysis.put("evaluator", parseJson(audit.getEvaluatorResult()));
        analysis.put("audit", parseJson(audit.getAuditResult()));
        return analysis;
    }

    private Object parseJson(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        try {
            return JSONObject.parse(raw);
        } catch (Exception ex) {
            return raw;
        }
    }

    private JSONObject parseJsonObject(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        try {
            return JSONObject.parseObject(raw);
        } catch (Exception ex) {
            return null;
        }
    }

    private String inferEmotionLabel(List<ChatRecord> records, JSONObject analysis) {
        JSONObject emotion = analysis.getJSONObject("emotion");
        if (emotion != null && emotion.getString("emotion") != null) {
            return emotion.getString("emotion");
        }
        return buildEmotionLabel(records);
    }

    private String inferRiskLabel(JSONObject analysis) {
        JSONObject crisis = analysis.getJSONObject("crisis");
        if (crisis != null && crisis.getString("level") != null) {
            return crisis.getString("level");
        }
        JSONObject intervention = analysis.getJSONObject("intervention");
        if (intervention != null && intervention.getString("intervention_level") != null) {
            return intervention.getString("intervention_level");
        }
        return "unknown";
    }

    private List<JSONObject> buildMessages(List<ChatRecord> records) {
        List<JSONObject> messages = new ArrayList<>();
        for (ChatRecord record : records) {
            JSONObject item = new JSONObject();
            item.put("id", record.getId());
            item.put("role", record.getRole());
            item.put("content", record.getContent());
            item.put("emotion", record.getEmotion());
            item.put("request_id", record.getRequestId());
            item.put("session_id", record.getSessionId());
            item.put("create_time", record.getCreateTime());
            messages.add(item);
        }
        return messages;
    }

    private JSONObject buildStatus(List<JSONObject> sessions, Long userId) {
        JSONObject status = new JSONObject();
        status.put("current_session", sessions.isEmpty() ? "暂无会话" : sessions.get(sessions.size() - 1).getString("title"));
        status.put("recent_session_count", sessions.size());
        status.put("highest_risk_level", inferHighestRisk(userId));
        status.put("rag_citation_count", inferRagCitationCount(userId));
        status.put("json_status", "valid");
        return status;
    }

    private String buildTitle(List<ChatRecord> records) {
        for (ChatRecord record : records) {
            if ("user".equals(record.getRole()) && record.getContent() != null && !record.getContent().isBlank()) {
                return compact(record.getContent(), 18);
            }
        }
        return records.isEmpty() ? "空会话" : "本机会话";
    }

    private String buildPreview(List<ChatRecord> records) {
        for (ChatRecord record : records) {
            if (record.getContent() != null && !record.getContent().isBlank()) {
                return compact(record.getContent(), 46);
            }
        }
        return "";
    }

    private String buildEmotionLabel(List<ChatRecord> records) {
        for (int i = records.size() - 1; i >= 0; i--) {
            String emotion = records.get(i).getEmotion();
            if (emotion != null && !emotion.isBlank()) {
                return emotion;
            }
        }
        return "unknown";
    }

    private String buildDayLabel(Object time) {
        if (!(time instanceof LocalDateTime createTime)) {
            return "更早";
        }
        LocalDateTime now = LocalDateTime.now();
        if (createTime.toLocalDate().equals(now.toLocalDate())) {
            return "今天";
        }
        if (createTime.toLocalDate().equals(now.minusDays(1).toLocalDate())) {
            return "昨天";
        }
        return "更早";
    }

    private String inferHighestRisk(Long userId) {
        var events = agentAuditEventMapper.findRecentByUserId(userId, 30);
        for (var event : events) {
            String crisis = event.getCrisisResult();
            if (crisis != null && crisis.contains("\"high\"")) {
                return "high";
            }
        }
        for (var event : events) {
            String crisis = event.getCrisisResult();
            if (crisis != null && (crisis.contains("\"medium\"") || crisis.contains("\"attention\""))) {
                return "medium";
            }
        }
        for (var event : events) {
            String crisis = event.getCrisisResult();
            if (crisis != null && crisis.contains("\"low\"")) {
                return "low";
            }
        }
        return "unknown";
    }

    private int inferRagCitationCount(Long userId) {
        var events = agentAuditEventMapper.findRecentByUserId(userId, 10);
        int count = 0;
        for (var event : events) {
            String rag = event.getRagResult();
            if (rag != null && !rag.isBlank() && !rag.equals("null")) {
                count++;
            }
        }
        return count;
    }

    private String compact(String text, int maxLength) {
        if (text == null) {
            return "";
        }
        String normalized = text.replaceAll("\\s+", " ").trim();
        return normalized.length() <= maxLength ? normalized : normalized.substring(0, maxLength) + "...";
    }
}
