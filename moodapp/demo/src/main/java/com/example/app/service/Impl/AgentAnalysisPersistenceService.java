package com.example.app.service.Impl;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import com.example.app.dto.python.PythonOrchestratorResponse;
import com.example.app.entity.AgentAuditEvent;
import com.example.app.entity.AgentEvaluation;
import com.example.app.entity.AgentRequestLog;
import com.example.app.entity.CrisisEventLog;
import com.example.app.entity.InterventionPlan;
import com.example.app.entity.InterventionFollowUp;
import com.example.app.entity.MentalState;
import com.example.app.entity.ModelCallLog;
import com.example.app.entity.PsychologicalProfile;
import com.example.app.entity.ProfileItem;
import com.example.app.entity.RagRetrievalLog;
import com.example.app.entity.RiskReport;
import com.example.app.entity.SafetyEventLog;
import com.example.app.mapper.AgentAuditEventMapper;
import com.example.app.mapper.AgentEvaluationMapper;
import com.example.app.mapper.AgentRequestLogMapper;
import com.example.app.mapper.CrisisEventLogMapper;
import com.example.app.mapper.InterventionPlanMapper;
import com.example.app.mapper.InterventionFollowUpMapper;
import com.example.app.mapper.MentalStateMapper;
import com.example.app.mapper.ModelCallLogMapper;
import com.example.app.mapper.ProfileMapper;
import com.example.app.mapper.ProfileItemMapper;
import com.example.app.mapper.RagRetrievalLogMapper;
import com.example.app.mapper.RiskReportMapper;
import com.example.app.mapper.SafetyEventLogMapper;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@Service
public class AgentAnalysisPersistenceService {

    @Resource
    private AgentRequestLogMapper agentRequestLogMapper;

    @Resource
    private SafetyEventLogMapper safetyEventLogMapper;

    @Resource
    private CrisisEventLogMapper crisisEventLogMapper;

    @Resource
    private RagRetrievalLogMapper ragRetrievalLogMapper;

    @Resource
    private ModelCallLogMapper modelCallLogMapper;

    @Resource
    private MentalStateMapper mentalStateMapper;

    @Resource
    private RiskReportMapper riskReportMapper;

    @Resource
    private ProfileMapper profileMapper;

    @Resource
    private ProfileItemMapper profileItemMapper;

    @Resource
    private InterventionPlanMapper interventionPlanMapper;

    @Resource
    private InterventionFollowUpMapper interventionFollowUpMapper;

    @Resource
    private AgentEvaluationMapper agentEvaluationMapper;

    @Resource
    private AgentAuditEventMapper agentAuditEventMapper;

    public PersistenceResult persist(
            Long userId,
            PythonOrchestratorResponse response,
            String originalMessage,
            String redactedMessage,
            long latencyMs
    ) {
        PersistenceResult result = new PersistenceResult();
        if (userId == null || response == null) {
            result.addFailure("context", "userId或response为空，跳过落库");
            return result;
        }

        persistStep(result, "agent_request_log", () -> persistAgentRequestLog(userId, response, originalMessage, redactedMessage, latencyMs));
        persistStep(result, "safety_event_log", () -> persistSafetyEventLog(userId, response));
        persistStep(result, "crisis_event_log", () -> persistCrisisEventLog(userId, response));
        persistStep(result, "rag_retrieval_log", () -> persistRagRetrievalLog(userId, response));
        persistStep(result, "model_call_log", () -> persistModelCallLog(userId, response, latencyMs));
        persistStep(result, "mental_state", () -> persistEmotionAnalysis(userId, response));
        persistStep(result, "risk_report", () -> persistRiskReport(userId, response));
        persistStep(result, "psychological_profile", () -> persistProfileSnapshot(userId, response.getProfile()));
        persistStep(result, "profile_item", () -> persistProfileItems(userId, response));
        persistStep(result, "intervention_plan", () -> persistInterventionPlan(userId, response));
        persistStep(result, "intervention_follow_up", () -> persistInterventionFollowUp(userId, response, originalMessage));
        persistStep(result, "agent_evaluation_record", () -> persistAgentEvaluation(userId, response));
        persistStep(result, "agent_audit_log", () -> persistAuditEvents(userId, response, latencyMs));
        return result;
    }

    private void persistStep(PersistenceResult result, String step, Runnable runnable) {
        try {
            runnable.run();
            result.addSuccess(step);
        } catch (Exception exception) {
            result.addFailure(step, exception.getMessage());
            System.err.println("[AgentAnalysisPersistenceService] Persist step failed, step="
                    + step + ", reason=" + exception.getMessage());
        }
    }

    private void persistAgentRequestLog(
            Long userId,
            PythonOrchestratorResponse response,
            String originalMessage,
            String redactedMessage,
            long latencyMs
    ) {
        AgentRequestLog log = new AgentRequestLog();
        log.setUserId(userId);
        log.setRequestId(truncate(response.getRequestId(), 120));
        log.setSessionId(truncate(response.getSessionId(), 120));
        log.setMessageHash(sha256(originalMessage));
        log.setRedactedMessageHash(sha256(redactedMessage));
        log.setAgentEntry("orchestrator");
        log.setWorkflowEngine("langgraph");
        log.setWorkflowVersion(truncate(resolvePromptVersions(response), 64));
        log.setModelName(truncate(response.getModel(), 120));
        log.setStatus("success");
        log.setErrorCode(null);
        log.setLatencyMs(latencyMs);
        log.setCreateTime(LocalDateTime.now());
        agentRequestLogMapper.insert(log);
    }

    private void persistSafetyEventLog(Long userId, PythonOrchestratorResponse response) {
        Map<String, Object> safety = response.getSafety();
        if (safety == null || safety.isEmpty()) {
            return;
        }

        SafetyEventLog log = new SafetyEventLog();
        log.setUserId(userId);
        log.setRequestId(truncate(response.getRequestId(), 120));
        log.setDecision(truncate(str(safety.get("decision")), 32));
        log.setViolations(truncate(JSON.toJSONString(safety.get("violations")), 2000));
        log.setPiiTypes(truncate(JSON.toJSONString(safety.get("pii_types")), 1000));
        log.setRequiresHuman(bool(firstExisting(safety, "requires_human", "requires_human_review")));
        log.setEvidence(truncate(JSON.toJSONString(safety.get("evidence")), 2000));
        log.setCreateTime(LocalDateTime.now());
        safetyEventLogMapper.insert(log);
    }

    private void persistCrisisEventLog(Long userId, PythonOrchestratorResponse response) {
        Map<String, Object> crisis = response.getCrisis();
        if (crisis == null || crisis.isEmpty()) {
            return;
        }

        CrisisEventLog log = new CrisisEventLog();
        log.setUserId(userId);
        log.setRequestId(truncate(response.getRequestId(), 120));
        log.setLevel(truncate(str(crisis.get("level")), 32));
        log.setSelfHarm(bool(crisis.get("self_harm")));
        log.setHarmToOthers(bool(crisis.get("harm_to_others")));
        log.setImmediacy(truncate(str(crisis.get("immediacy")), 32));
        log.setPlanPresent(bool(crisis.get("plan_present")));
        log.setToolPresent(bool(crisis.get("tool_present")));
        log.setTimePresent(bool(crisis.get("time_present")));
        log.setPlacePresent(bool(crisis.get("place_present")));
        log.setConfidence(number(crisis.get("confidence")));
        log.setEvidence(truncate(JSON.toJSONString(crisis.get("evidence")), 3000));
        log.setAction(truncate(str(crisis.get("action")), 64));
        log.setRequiresHumanReview(bool(firstExisting(crisis, "requires_human_review", "requires_human")));
        log.setHardRuleTriggered(bool(crisis.get("hard_rule_triggered")));
        log.setRuleHits(truncate(JSON.toJSONString(crisis.get("rule_hits")), 3000));
        log.setDecisionSource(truncate(str(crisis.get("decision_source")), 64));
        log.setCreateTime(LocalDateTime.now());
        crisisEventLogMapper.insert(log);
    }

    private void persistRagRetrievalLog(Long userId, PythonOrchestratorResponse response) {
        Map<String, Object> rag = response.getRag();
        if (rag == null || rag.isEmpty()) {
            return;
        }

        RagRetrievalLog log = new RagRetrievalLog();
        log.setUserId(userId);
        log.setRequestId(truncate(response.getRequestId(), 120));
        log.setQueryText(truncate(str(firstExisting(rag, "query_text", "query", "original_query")), 1000));
        log.setRewrittenQuery(truncate(str(firstExisting(rag, "rewritten_query", "search_query")), 1000));
        log.setSelectedCategories(safeJson(firstExisting(rag, "selected_categories", "categories"), 2000));
        log.setCitations(safeJson(compactRagCitations(firstExisting(rag, "citations", "results", "references")), 5000));
        log.setHasEvidence(boolWithDefault(firstExisting(rag, "has_evidence", "grounded"), hasRagCitations(rag)));
        log.setNoEvidenceReason(truncate(str(firstExisting(rag, "no_evidence_reason", "reason", "insufficient_reason")), 120));
        log.setRetrievalStrategy(truncate(str(firstExisting(rag, "retrieval_strategy", "strategy")), 120));
        log.setConfidence(number(rag.get("confidence")));
        log.setCreateTime(LocalDateTime.now());
        ragRetrievalLogMapper.insert(log);
    }

    private void persistModelCallLog(Long userId, PythonOrchestratorResponse response, long latencyMs) {
        ModelCallLog log = new ModelCallLog();
        log.setUserId(userId);
        log.setRequestId(truncate(response.getRequestId(), 120));
        log.setAgentName("orchestrator");
        log.setModelName(truncate(response.getModel(), 120));
        log.setPromptVersion(resolvePromptVersions(response));
        log.setInputTokens(0);
        log.setOutputTokens(0);
        log.setTotalTokens(0);
        log.setLatencyMs(latencyMs);
        log.setSuccess(true);
        log.setErrorCode(null);
        log.setCreateTime(LocalDateTime.now());
        modelCallLogMapper.insert(log);
    }

    private void persistEmotionAnalysis(Long userId, PythonOrchestratorResponse response) {
        Map<String, Object> emotion = response.getEmotion();
        Map<String, Object> crisis = response.getCrisis();
        Map<String, Object> risk = response.getRisk();
        if (emotion == null || emotion.isEmpty()) {
            return;
        }

        int anxiety = toJavaScore(emotion.get("anxiety"));
        int stress = toJavaScore(emotion.get("stress"));
        int depression = toJavaScore(emotion.get("depression"));
        double emotionRisk = round2(anxiety * 0.40 + stress * 0.35 + depression * 0.25);
        double trendRisk = toJavaScoreDouble(valueOf(risk, "trend_risk"));
        double riskScore = toJavaScoreDouble(valueOf(risk, "risk_score"));
        if (riskScore <= 0.0) {
            riskScore = emotionRisk;
        }

        String crisisLevel = lower(str(valueOf(crisis, "level")));
        if ("medium".equals(crisisLevel)) {
            riskScore = Math.max(riskScore, 60.0);
        } else if ("high".equals(crisisLevel) || "critical".equals(crisisLevel)) {
            riskScore = Math.max(riskScore, 90.0);
        }

        MentalState mentalState = new MentalState();
        mentalState.setUserId(userId);
        mentalState.setAnxiety(anxiety);
        mentalState.setStress(stress);
        mentalState.setDepression(depression);
        mentalState.setEmotionRisk(emotionRisk);
        mentalState.setTrendRisk(round2(trendRisk));
        mentalState.setRiskScore(round2(riskScore));
        mentalState.setCreateTime(LocalDateTime.now());
        mentalStateMapper.insert(mentalState);
    }

    private void persistRiskReport(Long userId, PythonOrchestratorResponse response) {
        Map<String, Object> crisis = response.getCrisis();
        Map<String, Object> intervention = response.getIntervention();
        Map<String, Object> safety = response.getSafety();
        Map<String, Object> evaluator = response.getEvaluator();
        Map<String, Object> rag = response.getRag();
        Map<String, Object> trend = response.getTrend();
        Map<String, Object> risk = response.getRisk();

        String riskLevel = lower(str(valueOf(risk, "risk_level")));
        if (riskLevel.isBlank()) {
            riskLevel = resolveRiskLevel(crisis, intervention);
        }
        boolean requiresHuman = bool(valueOf(risk, "requires_human_review"))
                || bool(valueOf(intervention, "requires_human_review"))
                || bool(valueOf(intervention, "requires_human"))
                || bool(valueOf(crisis, "requires_human"))
                || "medium".equals(riskLevel)
                || "high".equals(riskLevel)
                || "critical".equals(riskLevel);

        JSONObject reasons = new JSONObject();
        reasons.put("risk_score", valueOf(risk, "risk_score"));
        reasons.put("main_factors", valueOf(risk, "main_factors"));
        reasons.put("calculation_trace", valueOf(risk, "calculation_trace"));
        reasons.put("crisis_evidence", valueOf(crisis, "evidence"));
        reasons.put("intervention_reasoning", firstExisting(intervention, "reasoning", "rationale", "evidence"));
        reasons.put("evaluator", evaluator);

        JSONObject dangerSignals = new JSONObject();
        dangerSignals.put("safety_violations", valueOf(safety, "violations"));
        dangerSignals.put("crisis", crisis);

        JSONObject friendlyReport = new JSONObject();
        friendlyReport.put("reply", response.getReply());
        friendlyReport.put("intervention", intervention);
        friendlyReport.put("risk", risk);
        friendlyReport.put("trend", trend);
        friendlyReport.put("rag", rag);

        RiskReport riskReport = new RiskReport();
        riskReport.setUserId(userId);
        riskReport.setRiskLevel(riskLevel.isBlank() ? "unknown" : riskLevel);
        riskReport.setRiskReasons(truncate(JSON.toJSONString(reasons), 1800));
        riskReport.setDangerSignals(truncate(JSON.toJSONString(dangerSignals), 1800));
        Object recommendation = valueOf(risk, "recommendation");
        riskReport.setSuggestions(truncate(JSON.toJSONString(
                recommendation != null
                        ? recommendation
                        : firstExisting(intervention, "actions", "suggestions", "recommended_actions", "strategy")
        ), 1800));
        riskReport.setNeedCenter(requiresHuman ? "是" : "否");
        riskReport.setConclusion("Python多智能体评估：当前风险等级为 " + riskReport.getRiskLevel());
        riskReport.setUserFriendlyReport(truncate(JSON.toJSONString(friendlyReport), 1800));
        riskReport.setCreateTime(LocalDateTime.now());
        riskReportMapper.insert(riskReport);
    }

    private void persistProfileItems(Long userId, PythonOrchestratorResponse response) {
        Map<String, Object> profile = response.getProfile();
        if (profile == null || profile.isEmpty()) {
            return;
        }

        Object patchItems = profile.get("patch_items");
        if (!(patchItems instanceof List<?> items) || items.isEmpty()) {
            return;
        }

        for (Object rawItem : items) {
            if (!(rawItem instanceof Map<?, ?> rawMap)) {
                continue;
            }
            JSONObject itemJson = JSON.parseObject(JSON.toJSONString(rawMap));
            String category = str(itemJson.get("category"));
            String value = str(itemJson.get("value"));
            if (category.isBlank() || value.isBlank()) {
                continue;
            }

            String operation = lower(str(itemJson.get("operation")));
            ProfileItem item = new ProfileItem();
            item.setUserId(userId);
            item.setCategory(truncate(category, 80));
            item.setValue(truncate(value, 500));
            item.setEvidence(truncate(str(itemJson.get("evidence")), 800));
            item.setConfidence(number(itemJson.get("confidence")));
            item.setSource(truncate(str(itemJson.get("source")), 80));
            item.setEditable(boolWithDefault(itemJson.get("editable"), true));
            item.setDeletable(boolWithDefault(itemJson.get("deletable"), true));
            item.setSensitivity(truncate(str(itemJson.get("sensitivity")), 32));
            item.setStatus("delete".equals(operation) ? "deleted" : "active");
            item.setCreateTime(LocalDateTime.now());
            item.setUpdateTime(LocalDateTime.now());
            profileItemMapper.insert(item);
        }
    }

    private void persistProfileSnapshot(Long userId, Map<String, Object> profile) {
        if (profile == null || profile.isEmpty()) {
            return;
        }

        Object patch = firstExisting(profile, "patch_items", "profile_patch", "patches", "items", "profile");
        if (patch == null) {
            patch = profile;
        }

        PsychologicalProfile psychologicalProfile = new PsychologicalProfile();
        psychologicalProfile.setUserId(userId);
        psychologicalProfile.setEmotionTrait(truncate(JSON.toJSONString(firstExisting(
                profile,
                "emotion_trait",
                "emotional_state",
                "emotion"
        )), 500));
        psychologicalProfile.setStressTrait(truncate(JSON.toJSONString(firstExisting(
                profile,
                "stress_sources",
                "stress_source",
                "pressure_sources"
        )), 500));
        psychologicalProfile.setAnxietyTrait(truncate(JSON.toJSONString(firstExisting(
                profile,
                "communication_preference",
                "communication_preferences",
                "coping_styles"
        )), 500));
        psychologicalProfile.setRiskTrait(truncate(JSON.toJSONString(firstExisting(
                profile,
                "support_resources",
                "risk_factors",
                "protective_factors"
        )), 500));
        psychologicalProfile.setSummary(truncate(JSON.toJSONString(patch), 1800));
        psychologicalProfile.setCreateTime(LocalDateTime.now());
        profileMapper.insert(psychologicalProfile);
    }

    private void persistInterventionPlan(Long userId, PythonOrchestratorResponse response) {
        Map<String, Object> intervention = response.getIntervention();
        if (intervention == null || intervention.isEmpty()) {
            return;
        }

        InterventionPlan plan = new InterventionPlan();
        plan.setUserId(userId);
        Map<String, Object> followUp = response.getFollowUp();
        plan.setParentPlanId(longValue(followUp == null ? null : followUp.get("plan_id")));
        plan.setRevisionNo(interventionPlanMapper.nextRevisionNo(userId));
        String decisionSource = str(followUp == null ? "initial" : followUp.get("decision"));
        plan.setDecisionSource(truncate(decisionSource.isBlank() ? "initial" : decisionSource, 20));
        plan.setRequestId(truncate(response.getRequestId(), 80));
        plan.setInterventionLevel(truncate(str(firstExisting(intervention, "intervention_level", "risk_level", "level")), 40));
        plan.setRiskLevelSource(truncate(str(intervention.get("risk_level_source")), 80));
        plan.setStrategy(truncate(str(intervention.get("strategy")), 1000));
        plan.setActions(truncate(JSON.toJSONString(intervention.get("actions")), 3000));
        plan.setRationale(truncate(JSON.toJSONString(firstExisting(intervention, "rationale", "reasoning", "evidence")), 2000));
        plan.setSafetyConstraints(truncate(JSON.toJSONString(intervention.get("safety_constraints")), 2000));
        plan.setProfileUsed(truncate(JSON.toJSONString(intervention.get("profile_used")), 2000));
        plan.setRequiresHumanReview(bool(firstExisting(intervention, "requires_human_review", "requires_human")));
        plan.setRagCitationsUsed(truncate(JSON.toJSONString(firstExisting(intervention, "rag_citations_used", "rag_grounding")), 2000));
        plan.setConfidence(number(intervention.get("confidence")));
        plan.setCreateTime(LocalDateTime.now());
        interventionPlanMapper.insert(plan);
    }

    private void persistInterventionFollowUp(Long userId, PythonOrchestratorResponse response, String feedbackText) {
        Map<String, Object> followUp = response.getFollowUp();
        if (followUp == null || followUp.isEmpty()) {
            return;
        }
        InterventionFollowUp record = new InterventionFollowUp();
        record.setUserId(userId);
        record.setPlanId(longValue(followUp.get("plan_id")));
        record.setRequestId(truncate(response.getRequestId(), 80));
        record.setAdjustedPlanRequestId(truncate(response.getRequestId(), 80));
        record.setFeedbackText(truncate(feedbackText, 1000));
        record.setAdherence(truncate(str(followUp.get("adherence")), 32));
        record.setEffectiveness(truncate(str(followUp.get("effectiveness")), 32));
        record.setDecision(truncate(str(followUp.get("decision")), 32));
        record.setEmotionChange(truncate(str(followUp.get("emotion_change")), 64));
        record.setRiskChange(truncate(str(followUp.get("risk_change")), 64));
        record.setEvidence(truncate(JSON.toJSONString(followUp.get("evidence")), 1800));
        record.setAdjustmentReason(truncate(str(followUp.get("adjustment_reason")), 1000));
        record.setConfidence(number(followUp.get("confidence")));
        record.setCreateTime(LocalDateTime.now());
        interventionFollowUpMapper.insert(record);
    }

    private void persistAgentEvaluation(Long userId, PythonOrchestratorResponse response) {
        Map<String, Object> evaluator = response.getEvaluator();
        if (evaluator == null || evaluator.isEmpty()) {
            return;
        }

        AgentEvaluation evaluation = new AgentEvaluation();
        evaluation.setUserId(userId);
        evaluation.setRequestId(truncate(response.getRequestId(), 80));
        evaluation.setPassed(bool(evaluator.get("passed")));
        evaluation.setScore(number(evaluator.get("score")));
        evaluation.setAction(truncate(str(evaluator.get("action")), 64));
        evaluation.setIssues(truncate(JSON.toJSONString(evaluator.get("issues")), 3000));
        evaluation.setCheckedDimensions(truncate(JSON.toJSONString(evaluator.get("checked_dimensions")), 3000));
        evaluation.setCorrectedReply(truncate(str(evaluator.get("corrected_reply")), 3000));
        evaluation.setFinalReply(truncate(str(evaluator.get("final_reply")), 3000));
        evaluation.setRequiresHumanReview(bool(evaluator.get("requires_human_review")));
        evaluation.setRagGroundingScore(number(evaluator.get("rag_grounding_score")));
        evaluation.setCreateTime(LocalDateTime.now());
        agentEvaluationMapper.insert(evaluation);
    }

    private void persistAuditEvents(Long userId, PythonOrchestratorResponse response, long latencyMs) {
        Map<String, Object> audit = response.getAudit();
        if ((response.getTraceEvents() == null || response.getTraceEvents().isEmpty())
                && (audit == null || audit.isEmpty())) {
            return;
        }

        AgentAuditEvent summary = new AgentAuditEvent();
        summary.setUserId(userId);
        summary.setRequestId(truncate(response.getRequestId(), 80));
        summary.setSessionId(truncate(response.getSessionId(), 80));
        summary.setAgentTrace(safeJson(response.getTrace(), 3000));
        summary.setTraceEvents(safeJson(response.getTraceEvents(), 5000));
        summary.setSafetyResult(safeJson(response.getSafety(), 3000));
        summary.setCrisisResult(safeJson(response.getCrisis(), 3000));
        summary.setEmotionResult(safeJson(response.getEmotion(), 3000));
        summary.setRagResult(safeJson(compactRagForAudit(response.getRag()), 5000));
        summary.setProfileResult(safeJson(response.getProfile(), 5000));
        summary.setInterventionResult(safeJson(response.getIntervention(), 5000));
        summary.setEvaluatorResult(safeJson(response.getEvaluator(), 5000));
        summary.setAuditResult(safeJson(audit, 5000));
        summary.setModelName(truncate(response.getModel(), 120));
        summary.setWorkflowEngine("langgraph");
        summary.setWorkflowVersion(truncate(str(valueOf(audit, "prompt_version")), 64));
        summary.setLatencyMs(sumTraceDuration(response.getTraceEvents(), latencyMs));
        summary.setCreateTime(LocalDateTime.now());
        agentAuditEventMapper.insert(summary);
    }

    private String resolveRiskLevel(Map<String, Object> crisis, Map<String, Object> intervention) {
        String crisisLevel = lower(str(valueOf(crisis, "level")));
        String interventionLevel = lower(str(firstExisting(intervention, "risk_level", "level", "intervention_level")));

        if ("critical".equals(crisisLevel) || "critical".equals(interventionLevel)) return "critical";
        if ("high".equals(crisisLevel) || "high".equals(interventionLevel)) return "high";
        if ("medium".equals(crisisLevel) || "medium".equals(interventionLevel)) return "medium";
        if ("attention".equals(interventionLevel)) return "attention";
        if (!crisisLevel.isBlank()) return crisisLevel;
        return interventionLevel;
    }

    private Object valueOf(Map<String, Object> source, String key) {
        if (source == null || key == null) {
            return null;
        }
        return source.get(key);
    }

    private Object firstExisting(Map<String, Object> source, String... keys) {
        if (source == null || keys == null) {
            return null;
        }
        for (String key : keys) {
            Object value = source.get(key);
            if (value != null) {
                return value;
            }
        }
        return null;
    }

    private int toJavaScore(Object value) {
        double number = number(value);
        if (number <= 1.0) {
            number = number * 100.0;
        }
        return (int) Math.round(Math.max(0.0, Math.min(100.0, number)));
    }

    private double toJavaScoreDouble(Object value) {
        double score = number(value);
        if (score <= 1.0) {
            score *= 100.0;
        }
        return Math.max(0.0, Math.min(100.0, score));
    }

    private double number(Object value) {
        if (value == null) {
            return 0.0;
        }
        if (value instanceof Number number) {
            return number.doubleValue();
        }
        try {
            return Double.parseDouble(String.valueOf(value));
        } catch (Exception exception) {
            return 0.0;
        }
    }

    private Long longValue(Object value) {
        if (value == null) {
            return null;
        }
        try {
            return Long.valueOf(String.valueOf(value));
        } catch (NumberFormatException exception) {
            return null;
        }
    }

    private boolean bool(Object value) {
        if (value == null) {
            return false;
        }
        if (value instanceof Boolean booleanValue) {
            return booleanValue;
        }
        String text = lower(String.valueOf(value));
        return "true".equals(text) || "yes".equals(text) || "1".equals(text) || "是".equals(text);
    }

    private boolean boolWithDefault(Object value, boolean defaultValue) {
        if (value == null) {
            return defaultValue;
        }
        return bool(value);
    }

    private Long sumTraceDuration(List<Map<String, Object>> traceEvents, long fallbackLatencyMs) {
        if (traceEvents == null || traceEvents.isEmpty()) {
            return fallbackLatencyMs > 0 ? fallbackLatencyMs : null;
        }
        long total = 0L;
        boolean hasDuration = false;
        for (Map<String, Object> event : traceEvents) {
            if (event == null || event.get("duration_ms") == null) {
                continue;
            }
            total += Math.round(number(event.get("duration_ms")));
            hasDuration = true;
        }
        if (hasDuration) {
            return total;
        }
        return fallbackLatencyMs > 0 ? fallbackLatencyMs : null;
    }

    private boolean hasRagCitations(Map<String, Object> rag) {
        Object citations = firstExisting(rag, "citations", "results", "references");
        if (citations instanceof List<?> list) {
            return !list.isEmpty();
        }
        if (citations instanceof Map<?, ?> map) {
            return !map.isEmpty();
        }
        return citations != null && !String.valueOf(citations).isBlank();
    }

    private Object compactRagCitations(Object citations) {
        if (!(citations instanceof List<?> list)) {
            return citations;
        }

        JSONArray compacted = new JSONArray();
        int count = 0;
        for (Object raw : list) {
            if (count >= 8) {
                break;
            }
            JSONObject source = JSON.parseObject(JSON.toJSONString(raw));
            JSONObject item = new JSONObject();
            item.put("source", source.get("source"));
            item.put("category", source.get("category"));
            item.put("score", source.get("score"));
            item.put("document_id", source.get("document_id"));
            item.put("chunk_id", source.get("chunk_id"));
            item.put("file_name", source.get("file_name"));
            item.put("content_preview", truncate(str(source.get("content")), 600));
            compacted.add(item);
            count++;
        }
        return compacted;
    }

    private Object compactRagForAudit(Map<String, Object> rag) {
        if (rag == null || rag.isEmpty()) {
            return rag;
        }
        JSONObject compacted = new JSONObject();
        compacted.put("agent", rag.get("agent"));
        compacted.put("query", rag.get("query"));
        compacted.put("rewritten_query", rag.get("rewritten_query"));
        compacted.put("selected_categories", rag.get("selected_categories"));
        compacted.put("has_evidence", rag.get("has_evidence"));
        compacted.put("no_evidence_reason", rag.get("no_evidence_reason"));
        compacted.put("retrieval_strategy", rag.get("retrieval_strategy"));
        compacted.put("confidence", rag.get("confidence"));
        compacted.put("prompt_version", rag.get("prompt_version"));
        compacted.put("citations", compactRagCitations(firstExisting(rag, "citations", "results", "references")));
        return compacted;
    }

    private String resolvePromptVersions(PythonOrchestratorResponse response) {
        Map<String, Object> audit = response.getAudit();
        Object versions = valueOf(audit, "versions");
        if (versions != null) {
            return truncate(JSON.toJSONString(versions), 120);
        }

        Object promptVersion = valueOf(response.getEvaluator(), "prompt_version");
        if (promptVersion != null) {
            return truncate(str(promptVersion), 120);
        }
        return null;
    }

    private String sha256(String value) {
        if (value == null) {
            return null;
        }
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] encoded = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder builder = new StringBuilder();
            for (byte item : encoded) {
                builder.append(String.format("%02x", item));
            }
            return builder.toString();
        } catch (Exception exception) {
            return Integer.toHexString(value.hashCode());
        }
    }

    private String str(Object value) {
        return value == null ? "" : String.valueOf(value);
    }

    private String lower(String value) {
        return value == null ? "" : value.trim().toLowerCase();
    }

    private double round2(double value) {
        return Math.round(value * 100.0) / 100.0;
    }

    private String truncate(String value, int maxLength) {
        if (value == null) {
            return "";
        }
        if (value.length() <= maxLength) {
            return value;
        }
        return value.substring(0, maxLength);
    }

    private String safeJson(Object value, int maxLength) {
        if (value == null) {
            return null;
        }
        String raw = JSON.toJSONString(value);
        if (raw == null || raw.length() <= maxLength) {
            return raw;
        }

        JSONObject wrapped = new JSONObject();
        wrapped.put("truncated", true);
        wrapped.put("original_length", raw.length());
        wrapped.put("preview", truncate(raw, Math.max(80, maxLength - 120)));
        return JSON.toJSONString(wrapped);
    }

    public static class PersistenceResult {
        private final List<String> savedSteps = new ArrayList<>();
        private final List<JSONObject> failedSteps = new ArrayList<>();

        public boolean isSaved() {
            return failedSteps.isEmpty() && !savedSteps.isEmpty();
        }

        public boolean isPartial() {
            return !savedSteps.isEmpty() && !failedSteps.isEmpty();
        }

        public List<String> getSavedSteps() {
            return savedSteps;
        }

        public List<JSONObject> getFailedSteps() {
            return failedSteps;
        }

        private void addSuccess(String step) {
            savedSteps.add(step);
        }

        private void addFailure(String step, String reason) {
            JSONObject failure = new JSONObject();
            failure.put("step", step);
            failure.put("reason", reason);
            failedSteps.add(failure);
        }
    }
}
