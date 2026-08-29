package com.example.app.controller;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import com.example.app.dto.ApiResponse;
import com.example.app.entity.AgentAuditEvent;
import com.example.app.entity.AgentEvaluation;
import com.example.app.entity.AgentRequestLog;
import com.example.app.entity.RagRetrievalLog;
import com.example.app.mapper.AgentAuditEventMapper;
import com.example.app.mapper.AgentEvaluationMapper;
import com.example.app.mapper.AgentRequestLogMapper;
import com.example.app.mapper.RagRetrievalLogMapper;
import jakarta.annotation.Resource;
import jakarta.servlet.http.HttpServletRequest;
import com.example.app.utils.AuthenticatedUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.List;

@RestController
@RequestMapping("/agent/audit")
public class AgentAuditController {

    @Resource
    private AgentAuditEventMapper agentAuditEventMapper;

    @Resource
    private AgentRequestLogMapper agentRequestLogMapper;

    @Resource
    private RagRetrievalLogMapper ragRetrievalLogMapper;

    @Resource
    private AgentEvaluationMapper agentEvaluationMapper;

    @GetMapping("/events")
    public ApiResponse<JSONObject> events(
            @RequestParam(required = false) Long userId,
            @RequestParam(defaultValue = "30") int limit,
            HttpServletRequest request
    ) {
        userId = AuthenticatedUser.requireId(request);
        int safeLimit = Math.max(1, Math.min(limit, 100));
        List<AgentAuditEvent> events = agentAuditEventMapper.findRecentByUserId(userId, safeLimit);

        JSONArray items = new JSONArray();
        for (AgentAuditEvent event : events) {
            items.add(buildEventSummary(event));
        }

        JSONObject result = new JSONObject();
        result.put("total", items.size());
        result.put("items", items);
        return ApiResponse.success(result);
    }

    @GetMapping("/events/{requestId}")
    public ApiResponse<JSONObject> detail(@PathVariable String requestId, HttpServletRequest request) {
        AgentAuditEvent audit = agentAuditEventMapper.findByRequestId(requestId);
        if (audit == null || !AuthenticatedUser.requireId(request).equals(audit.getUserId())) {
            return ApiResponse.error(404, "审计记录不存在");
        }

        AgentRequestLog requestLog = agentRequestLogMapper.findByRequestId(requestId);
        RagRetrievalLog rag = ragRetrievalLogMapper.findByRequestId(requestId);
        AgentEvaluation evaluation = agentEvaluationMapper.findByRequestId(requestId);

        JSONObject result = buildEventSummary(audit);
        result.put("request_log", buildRequestLog(requestLog));
        result.put("trace_timeline", buildTraceTimeline(audit));
        result.put("safety", parseJson(audit.getSafetyResult()));
        result.put("crisis", parseJson(audit.getCrisisResult()));
        result.put("emotion", parseJson(audit.getEmotionResult()));
        result.put("rag", buildRag(rag, audit));
        result.put("profile", parseJson(audit.getProfileResult()));
        result.put("intervention", parseJson(audit.getInterventionResult()));
        result.put("evaluator", buildEvaluator(evaluation, audit));
        result.put("audit", parseJson(audit.getAuditResult()));
        return ApiResponse.success(result);
    }

    @GetMapping("/events/{requestId}/trace")
    public ApiResponse<JSONObject> trace(@PathVariable String requestId, HttpServletRequest request) {
        AgentAuditEvent audit = agentAuditEventMapper.findByRequestId(requestId);
        if (audit == null || !AuthenticatedUser.requireId(request).equals(audit.getUserId())) {
            return ApiResponse.error(404, "审计记录不存在");
        }

        JSONObject result = new JSONObject();
        result.put("request_id", requestId);
        result.put("agent_trace", parseJson(audit.getAgentTrace()));
        result.put("trace_events", parseJson(audit.getTraceEvents()));
        result.put("timeline", buildTraceTimeline(audit));
        return ApiResponse.success(result);
    }

    private JSONObject buildEventSummary(AgentAuditEvent event) {
        JSONObject audit = parseObject(event.getAuditResult());
        JSONObject decisions = audit == null ? null : audit.getJSONObject("decisions");
        JSONObject traceSummary = audit == null ? null : audit.getJSONObject("trace_summary");
        JSONObject routing = audit == null ? null : audit.getJSONObject("routing");

        JSONObject item = new JSONObject();
        item.put("request_id", event.getRequestId());
        item.put("user_id", event.getUserId());
        item.put("session_id", event.getSessionId());
        item.put("model_name", event.getModelName());
        item.put("workflow_engine", event.getWorkflowEngine());
        item.put("workflow_version", event.getWorkflowVersion());
        item.put("latency_ms", event.getLatencyMs());
        item.put("create_time", event.getCreateTime());
        item.put("status", audit == null ? "unknown" : audit.getString("status"));
        item.put("crisis_level", pick(decisions, "crisis_level"));
        item.put("emotion_label", pick(decisions, "emotion_label"));
        item.put("intervention_level", pick(decisions, "intervention_level"));
        item.put("requires_human_review", decisions != null && Boolean.TRUE.equals(decisions.getBoolean("requires_human_review")));
        item.put("evaluator_passed", decisions == null ? null : decisions.get("evaluator_passed"));
        item.put("trace_event_count", traceSummary == null ? null : traceSummary.get("trace_event_count"));
        item.put("route", traceSummary == null ? null : traceSummary.get("route"));
        item.put("routing_policy_version", routing == null ? null : routing.get("policy_version"));
        item.put("hard_constraint_triggered", routing != null && Boolean.TRUE.equals(routing.getBoolean("hard_constraint_triggered")));
        return item;
    }

    private JSONObject buildRequestLog(AgentRequestLog log) {
        if (log == null) {
            return null;
        }
        JSONObject item = new JSONObject();
        item.put("request_id", log.getRequestId());
        item.put("session_id", log.getSessionId());
        item.put("message_hash", log.getMessageHash());
        item.put("redacted_message_hash", log.getRedactedMessageHash());
        item.put("agent_entry", log.getAgentEntry());
        item.put("status", log.getStatus());
        item.put("error_code", log.getErrorCode());
        item.put("latency_ms", log.getLatencyMs());
        item.put("create_time", log.getCreateTime());
        return item;
    }

    private JSONArray buildTraceTimeline(AgentAuditEvent audit) {
        Object raw = parseJson(audit.getTraceEvents());
        if (!(raw instanceof JSONArray events)) {
            return new JSONArray();
        }

        JSONArray timeline = new JSONArray();
        for (Object rawEvent : events) {
            JSONObject event = JSON.parseObject(JSON.toJSONString(rawEvent));
            JSONObject item = new JSONObject();
            item.put("agent", event.getString("agent"));
            item.put("status", event.getString("status"));
            item.put("duration_ms", event.get("duration_ms"));
            item.put("error_code", event.get("error_code"));
            item.put("started_at", event.get("started_at"));
            item.put("finished_at", event.get("finished_at"));
            item.put("metadata", event.get("metadata"));
            timeline.add(item);
        }
        return timeline;
    }

    private JSONObject buildRag(RagRetrievalLog rag, AgentAuditEvent audit) {
        JSONObject result = new JSONObject();
        result.put("audit_result", parseJson(audit.getRagResult()));
        if (rag == null) {
            return result;
        }
        result.put("query_text", rag.getQueryText());
        result.put("rewritten_query", rag.getRewrittenQuery());
        result.put("selected_categories", parseJson(rag.getSelectedCategories()));
        result.put("citations", parseJson(rag.getCitations()));
        result.put("has_evidence", rag.getHasEvidence());
        result.put("no_evidence_reason", rag.getNoEvidenceReason());
        result.put("retrieval_strategy", rag.getRetrievalStrategy());
        result.put("confidence", rag.getConfidence());
        result.put("create_time", rag.getCreateTime());
        return result;
    }

    private JSONObject buildEvaluator(AgentEvaluation evaluation, AgentAuditEvent audit) {
        JSONObject result = new JSONObject();
        result.put("audit_result", parseJson(audit.getEvaluatorResult()));
        if (evaluation == null) {
            return result;
        }
        result.put("passed", evaluation.getPassed());
        result.put("score", evaluation.getScore());
        result.put("action", evaluation.getAction());
        result.put("issues", parseJson(evaluation.getIssues()));
        result.put("checked_dimensions", parseJson(evaluation.getCheckedDimensions()));
        result.put("requires_human_review", evaluation.getRequiresHumanReview());
        result.put("rag_grounding_score", evaluation.getRagGroundingScore());
        result.put("final_reply", evaluation.getFinalReply());
        result.put("create_time", evaluation.getCreateTime());
        return result;
    }

    private Object parseJson(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        try {
            return JSON.parse(raw);
        } catch (Exception exception) {
            return raw;
        }
    }

    private JSONObject parseObject(String raw) {
        Object parsed = parseJson(raw);
        if (parsed instanceof JSONObject object) {
            return object;
        }
        return null;
    }

    private Object pick(JSONObject object, String key) {
        return object == null ? null : object.get(key);
    }
}
