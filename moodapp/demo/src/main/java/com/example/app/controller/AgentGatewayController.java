package com.example.app.controller;

import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONObject;
import com.example.app.dto.ApiResponse;
import com.example.app.dto.python.PythonAgentContext;
import com.example.app.dto.python.PythonChatMessage;
import com.example.app.dto.python.PythonOrchestratorRequest;
import com.example.app.dto.python.PythonOrchestratorResponse;
import com.example.app.entity.AgentAuditEvent;
import com.example.app.entity.MentalState;
import com.example.app.entity.InterventionPlan;
import com.example.app.entity.PsychologicalProfile;
import com.example.app.mapper.AgentAuditEventMapper;
import com.example.app.mapper.InterventionPlanMapper;
import com.example.app.mapper.InterventionActionFeedbackMapper;
import com.example.app.mapper.MentalStateMapper;
import com.example.app.mapper.ProfileMapper;
import com.example.app.service.ChatRecordService;
import com.example.app.service.Impl.AgentAnalysisPersistenceService;
import com.example.app.service.Impl.PythonOrchestratorService;
import jakarta.annotation.Resource;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;
import org.springframework.data.redis.core.RedisTemplate;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpServletRequest;

import java.io.IOException;
import java.io.OutputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

@RestController
@RequestMapping("/agent/gateway")
public class AgentGatewayController {

    private static final int REDIS_CONTEXT_LIMIT = 20;
    private static final long REDIS_CONTEXT_TTL_MINUTES = 30L;
    private static final int MAX_TREND_POINTS = 30;
    private static final String PROACTIVE_GREETING_PROMPT =
            "请结合已有对话上下文，主动开启一次简短、自然、温和的心理陪伴对话。"
                    + "不要假装用户刚刚说过话，不做诊断，不超过120字。";

    @Resource
    private PythonOrchestratorService pythonOrchestratorService;

    @Resource
    private AgentAnalysisPersistenceService agentAnalysisPersistenceService;

    @Resource
    private ChatRecordService chatRecordService;

    @Resource
    private RedisTemplate<String, Object> redisTemplate;

    @Resource
    private MentalStateMapper mentalStateMapper;

    @Resource
    private AgentAuditEventMapper agentAuditEventMapper;

    @Resource
    private InterventionPlanMapper interventionPlanMapper;

    @Resource
    private InterventionActionFeedbackMapper interventionActionFeedbackMapper;

    @Resource
    private ProfileMapper profileMapper;

    @GetMapping("/health")
    public ApiResponse<JSONObject> health() {
        return ApiResponse.success(pythonOrchestratorService.health());
    }

    @GetMapping("/ready")
    public ApiResponse<JSONObject> ready() {
        return ApiResponse.success(pythonOrchestratorService.ready());
    }

    @GetMapping("/model/status")
    public ApiResponse<JSONObject> modelStatus() {
        return ApiResponse.success(pythonOrchestratorService.modelStatus());
    }

    @GetMapping("/agents/registry")
    public ApiResponse<JSONObject> agentRegistry() {
        return ApiResponse.success(pythonOrchestratorService.agentRegistry());
    }

    @GetMapping("/rag/status")
    public ApiResponse<JSONObject> ragStatus() {
        return ApiResponse.success(pythonOrchestratorService.ragStatus());
    }

    @PostMapping("/rag/search")
    public ApiResponse<JSONObject> ragSearch(@RequestBody(required = false) JSONObject body) {
        return ApiResponse.success(pythonOrchestratorService.ragSearch(body));
    }

    @GetMapping("/evaluation/redteam/latest-summary")
    public ApiResponse<JSONObject> latestEvaluationSummary() {
        return ApiResponse.success(pythonOrchestratorService.latestEvaluationSummary());
    }

    @GetMapping("/evaluation/redteam/latest-report")
    public ApiResponse<JSONObject> latestEvaluationReport() {
        return ApiResponse.success(pythonOrchestratorService.latestEvaluationReport());
    }

    @GetMapping("/evaluation/redteam/cases")
    public ApiResponse<JSONObject> redteamCases() {
        return ApiResponse.success(pythonOrchestratorService.redteamCases());
    }

    @PostMapping("/orchestrate")
    public ApiResponse<PythonOrchestratorResponse> orchestrate(
            @RequestBody PythonOrchestratorRequest request,
            HttpServletRequest httpRequest
    ) {
        if (request == null || request.getMessage() == null || request.getMessage().isBlank()) {
            return ApiResponse.error(400, "message不能为空");
        }
        bindAuthenticatedUser(request, httpRequest);
        return ApiResponse.success(executeOrchestration(request));
    }

    @PostMapping(value = "/orchestrate/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public StreamingResponseBody orchestrateStream(
            @RequestBody PythonOrchestratorRequest request,
            HttpServletResponse httpResponse,
            HttpServletRequest httpRequest
    ) {
        httpResponse.setCharacterEncoding("UTF-8");
        httpResponse.setContentType("text/event-stream;charset=UTF-8");
        httpResponse.setHeader("Cache-Control", "no-cache, no-transform");
        httpResponse.setHeader("X-Accel-Buffering", "no");
        if (request != null) {
            bindAuthenticatedUser(request, httpRequest);
        }
        return outputStream -> {
            if (request == null || request.getMessage() == null || request.getMessage().isBlank()) {
                writeSse(outputStream, "error", Map.of("message", "message不能为空"));
                return;
            }
            try {
                writeSse(outputStream, "status", Map.of(
                        "phase", "accepted",
                        "message", "已连接，正在进行安全与情绪分析"
                ));
                PythonOrchestratorResponse response = executeStreamingOrchestration(request);
                writeSse(outputStream, "status", Map.of(
                        "phase", "reply",
                        "message", "安全校验完成，正在生成回复"
                ));
                // Only the evaluated and display-sanitized reply is streamed.
                // The browser still gets a typing effect without exposing raw
                // model output or internal RAG identifiers.
                writeSse(outputStream, "delta", Map.of("content", response.getReply()));
                writeSse(outputStream, "result", response);
                writeSse(outputStream, "done", Map.of(
                        "request_id", response.getRequestId() == null ? "" : response.getRequestId()
                ));
            } catch (IOException clientDisconnected) {
                // 浏览器刷新、关闭页面或主动取消请求时，SSE连接会正常中断。
                // 此时不能继续向已经关闭的连接写error事件。
            } catch (Exception exception) {
                try {
                    writeSse(outputStream, "error", Map.of(
                            "message", safeErrorMessage(exception)
                    ));
                } catch (IOException clientDisconnected) {
                    // 客户端已离开，服务端无需继续写入。
                }
            }
        };
    }

    @PostMapping(value = "/init/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public StreamingResponseBody proactiveGreetingStream(
            @RequestBody(required = false) PythonOrchestratorRequest request,
            HttpServletResponse httpResponse,
            HttpServletRequest httpRequest
    ) {
        httpResponse.setCharacterEncoding("UTF-8");
        httpResponse.setContentType("text/event-stream;charset=UTF-8");
        httpResponse.setHeader("Cache-Control", "no-cache, no-transform");
        httpResponse.setHeader("X-Accel-Buffering", "no");
        PythonOrchestratorRequest authenticatedRequest = request == null
                ? new PythonOrchestratorRequest()
                : request;
        bindAuthenticatedUser(authenticatedRequest, httpRequest);
        return outputStream -> {
            try {
                writeSse(outputStream, "status", Map.of(
                        "phase", "init",
                        "message", "心晴正在准备问候"
                ));
                PythonAgentContext context = normalizeContext(authenticatedRequest.getContext());
                HistoryResolution historyResolution = resolveRedisHistory(
                        context.getUserId(), context.getSessionId()
                );
                context.getMetadata().put("init", true);
                context.getMetadata().put("proactive", true);
                context.getMetadata().put("java_service", "AgentGatewayController.proactiveGreetingStream");
                context.getMetadata().put("history_source", historyResolution.source);
                context.getMetadata().put("history_message_count", historyResolution.messages.size());

                PythonOrchestratorResponse response = pythonOrchestratorService.orchestrateStream(
                        context.getUserId(),
                        context.getSessionId(),
                        context.getRequestId(),
                        PROACTIVE_GREETING_PROMPT,
                        historyResolution.messages,
                        context.getMetadata(),
                        true,
                        content -> writeSseUnchecked(outputStream, content)
                );
                response.setReply(extractMainReply(response.getReply()));
                writeSse(outputStream, "result", response);
                writeSse(outputStream, "done", Map.of(
                        "request_id", response.getRequestId() == null ? "" : response.getRequestId()
                ));
            } catch (IOException clientDisconnected) {
                // 页面离开后不再继续写入。
            } catch (Exception exception) {
                try {
                    writeSse(outputStream, "error", Map.of("message", safeErrorMessage(exception)));
                } catch (IOException clientDisconnected) {
                    // 客户端已经离开。
                }
            }
        };
    }

    private PythonOrchestratorResponse executeOrchestration(PythonOrchestratorRequest request) {
        long start = System.currentTimeMillis();

        PythonAgentContext context = normalizeContext(request.getContext());
        HistoryResolution historyResolution = resolveRedisHistory(
                context.getUserId(), context.getSessionId()
        );
        context.getMetadata().put("history_source", historyResolution.source);
        context.getMetadata().put("history_message_count", historyResolution.messages.size());
        context.getMetadata().put("trend_points", buildTrendPoints(context.getUserId()));
        JSONObject latestIntervention = loadLatestIntervention(context.getUserId());
        if (latestIntervention != null && !latestIntervention.isEmpty()) {
            context.getMetadata().put("latest_intervention", latestIntervention);
            putActionFeedbackContext(context, latestIntervention);
        }
        JSONObject latestProfile = loadLatestProfile(context.getUserId());
        if (latestProfile != null && !latestProfile.isEmpty()) {
            context.getMetadata().put("profile", latestProfile);
        }
        JSONObject crisisState = loadCrisisState(context.getUserId(), context.getSessionId());
        if (crisisState != null && !crisisState.isEmpty()) {
            context.getMetadata().put("crisis_state", crisisState);
        }

        PythonOrchestratorResponse response = pythonOrchestratorService.orchestrate(
                context.getUserId(),
                context.getSessionId(),
                context.getRequestId(),
                request.getMessage(),
                historyResolution.messages,
                context.getMetadata()
        );

        String redactedMessage = resolveRedactedMessage(response, request.getMessage());
        ChatRecordWriteResult chatRecordResult = persistChatRecords(
                context.getUserId(),
                redactedMessage,
                response
        );
        saveRedisHistory(context.getUserId(), context.getSessionId(), redactedMessage, response.getReply());
        AgentAnalysisPersistenceService.PersistenceResult analysisResult =
                agentAnalysisPersistenceService.persist(
                        context.getUserId(),
                        response,
                        request.getMessage(),
                        redactedMessage,
                        System.currentTimeMillis() - start
                );

        // 持久化完成后再提取主要回答文本。数据库和分析服务仍接收 Python
        // 返回的原始 response，只有返回给浏览器的 response.reply 做展示层清理。
        response.setReply(extractMainReply(response.getReply()));

        response.setPersistence(buildPersistence(
                context.getUserId(),
                analysisResult,
                chatRecordResult,
                historyResolution
        ));
        return response;
    }

    private PythonOrchestratorResponse executeStreamingOrchestration(
            PythonOrchestratorRequest request
    ) {
        long start = System.currentTimeMillis();
        PythonAgentContext context = normalizeContext(request.getContext());
        HistoryResolution historyResolution = resolveRedisHistory(
                context.getUserId(), context.getSessionId()
        );
        context.getMetadata().put("history_source", historyResolution.source);
        context.getMetadata().put("history_message_count", historyResolution.messages.size());
        context.getMetadata().put("trend_points", buildTrendPoints(context.getUserId()));
        JSONObject latestIntervention = loadLatestIntervention(context.getUserId());
        if (latestIntervention != null && !latestIntervention.isEmpty()) {
            context.getMetadata().put("latest_intervention", latestIntervention);
            putActionFeedbackContext(context, latestIntervention);
        }
        JSONObject latestProfile = loadLatestProfile(context.getUserId());
        if (latestProfile != null && !latestProfile.isEmpty()) {
            context.getMetadata().put("profile", latestProfile);
        }
        JSONObject crisisState = loadCrisisState(context.getUserId(), context.getSessionId());
        if (crisisState != null && !crisisState.isEmpty()) {
            context.getMetadata().put("crisis_state", crisisState);
        }

        // The browser endpoint remains SSE, but the Python workflow uses its
        // evaluated non-streaming path. Java already buffers the answer until
        // evaluation completes, so invoking Python's raw token stream only
        // adds a second model attempt on stream failure and raises fallback
        // probability without improving the visible UX.
        PythonOrchestratorResponse response = pythonOrchestratorService.orchestrate(
                context.getUserId(),
                context.getSessionId(),
                context.getRequestId(),
                request.getMessage(),
                historyResolution.messages,
                context.getMetadata()
        );
        String redactedMessage = resolveRedactedMessage(response, request.getMessage());
        ChatRecordWriteResult chatRecordResult = persistChatRecords(
                context.getUserId(), redactedMessage, response
        );
        saveRedisHistory(context.getUserId(), context.getSessionId(), redactedMessage, response.getReply());
        AgentAnalysisPersistenceService.PersistenceResult analysisResult =
                agentAnalysisPersistenceService.persist(
                        context.getUserId(), response, request.getMessage(), redactedMessage,
                        System.currentTimeMillis() - start
                );
        response.setReply(extractMainReply(response.getReply()));
        response.setPersistence(buildPersistence(
                context.getUserId(), analysisResult, chatRecordResult, historyResolution
        ));
        return response;
    }

    private void writeSseUnchecked(OutputStream outputStream, String content) {
        try {
            writeSse(outputStream, "delta", Map.of("content", content));
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        }
    }

    private JSONObject loadCrisisState(Long userId, String sessionId) {
        if (userId == null || sessionId == null || sessionId.isBlank()) {
            return null;
        }
        try {
            AgentAuditEvent latest = agentAuditEventMapper.findLatestByUserAndSession(userId, sessionId);
            if (latest == null || latest.getCrisisResult() == null || latest.getCrisisResult().isBlank()) {
                return null;
            }
            JSONObject crisisResult = JSON.parseObject(latest.getCrisisResult());
            return crisisResult == null ? null : crisisResult.getJSONObject("history_state");
        } catch (Exception exception) {
            System.err.println("[AgentGatewayController] 危机会话状态读取失败，本轮按文本历史继续: "
                    + safeErrorMessage(exception));
            return null;
        }
    }

    /**
     * 将最近一次正式干预方案作为跟进路由的上下文，而非让 Python 依赖浏览器传参。
     */
    private JSONObject loadLatestIntervention(Long userId) {
        if (userId == null) {
            return null;
        }
        try {
            InterventionPlan plan = interventionPlanMapper.findLatestByUserId(userId);
            if (plan == null) {
                return null;
            }
            JSONObject result = new JSONObject();
            result.put("id", plan.getId());
            result.put("parent_plan_id", plan.getParentPlanId());
            result.put("revision_no", plan.getRevisionNo());
            result.put("decision_source", plan.getDecisionSource());
            result.put("request_id", plan.getRequestId());
            result.put("intervention_level", plan.getInterventionLevel());
            result.put("risk_level_source", plan.getRiskLevelSource());
            result.put("strategy", plan.getStrategy());
            result.put("actions", plan.getActions());
            result.put("rationale", plan.getRationale());
            result.put("requires_human_review", plan.getRequiresHumanReview());
            result.put("create_time", plan.getCreateTime() == null ? null : plan.getCreateTime().toString());
            return result;
        } catch (Exception exception) {
            System.err.println("[AgentGatewayController] 最近干预方案读取失败，本轮不触发跟进路由: "
                    + safeErrorMessage(exception));
            return null;
        }
    }

    /** 只把当前方案的动作反馈交给 Python，避免旧方案反馈重复触发下一轮调整。 */
    private void putActionFeedbackContext(PythonAgentContext context, JSONObject latestIntervention) {
        if (context.getUserId() == null || latestIntervention.getLong("id") == null) {
            return;
        }
        try {
            context.getMetadata().put("action_feedbacks", interventionActionFeedbackMapper.findRecentByPlanIdAndUserId(
                    latestIntervention.getLong("id"), context.getUserId(), 20));
        } catch (Exception exception) {
            System.err.println("[AgentGatewayController] 动作反馈读取失败，本轮仍按文本跟进: "
                    + safeErrorMessage(exception));
        }
    }

    private JSONObject loadLatestProfile(Long userId) {
        if (userId == null) {
            return null;
        }
        try {
            PsychologicalProfile profile = profileMapper.findLatest(userId);
            if (profile == null) {
                return null;
            }
            JSONObject result = new JSONObject();
            result.put("emotion_trait", profile.getEmotionTrait());
            result.put("stress_sources", profile.getStressTrait());
            result.put("communication_preference", profile.getAnxietyTrait());
            result.put("support_resources", profile.getRiskTrait());
            result.put("summary", profile.getSummary());
            return result;
        } catch (Exception exception) {
            System.err.println("[AgentGatewayController] 最新画像读取失败，本轮按无画像继续: "
                    + safeErrorMessage(exception));
            return null;
        }
    }

    private void writeSse(OutputStream outputStream, String event, Object data) throws IOException {
        String payload = "event: " + event + "\n"
                + "data: " + JSON.toJSONString(data) + "\n\n";
        outputStream.write(payload.getBytes(StandardCharsets.UTF_8));
        outputStream.flush();
    }

    private JSONArray buildTrendPoints(Long userId) {
        JSONArray points = new JSONArray();
        if (userId == null) {
            return points;
        }
        List<MentalState> states;
        try {
            states = mentalStateMapper.findLatestHistory(userId, MAX_TREND_POINTS);
        } catch (Exception exception) {
            System.err.println("[AgentGatewayController] 趋势历史读取失败，本轮按数据不足继续: "
                    + exception.getMessage());
            return points;
        }
        if (states == null || states.isEmpty()) {
            return points;
        }
        states.stream()
                .sorted(Comparator.comparing(
                        MentalState::getCreateTime,
                        Comparator.nullsLast(Comparator.naturalOrder())
                ))
                .forEach(state -> {
                    JSONObject point = new JSONObject();
                    LocalDateTime timestamp = state.getCreateTime() == null
                            ? LocalDateTime.now()
                            : state.getCreateTime();
                    point.put("timestamp", timestamp.atOffset(ZoneOffset.ofHours(8)).toInstant().toString());
                    point.put("anxiety", toInternalScore(state.getAnxiety()));
                    point.put("stress", toInternalScore(state.getStress()));
                    point.put("depression", toInternalScore(state.getDepression()));
                    point.put("intervention", false);
                    point.put("intervention_type", null);
                    points.add(point);
                });
        return points;
    }

    private double toInternalScore(Number value) {
        if (value == null) {
            return 0.0;
        }
        double score = value.doubleValue();
        if (score > 1.0) {
            score /= 100.0;
        }
        return Math.max(0.0, Math.min(1.0, score));
    }

    private PythonAgentContext normalizeContext(PythonAgentContext context) {
        PythonAgentContext normalized = context == null ? new PythonAgentContext() : context;
        if (normalized.getRequestId() == null || normalized.getRequestId().isBlank()) {
            normalized.setRequestId(UUID.randomUUID().toString());
        }
        if (normalized.getSessionId() == null || normalized.getSessionId().isBlank()) {
            normalized.setSessionId("session-" + UUID.randomUUID());
        }
        if (normalized.getMetadata() == null) {
            normalized.setMetadata(new HashMap<>());
        }
        normalized.getMetadata().putIfAbsent("entrypoint", "java_agent_gateway");
        return normalized;
    }

    private void bindAuthenticatedUser(
            PythonOrchestratorRequest request,
            HttpServletRequest httpRequest
    ) {
        Object authenticatedUserId = httpRequest.getAttribute("userId");
        if (!(authenticatedUserId instanceof Long userId)) {
            throw new IllegalStateException("缺少已认证用户身份");
        }
        PythonAgentContext context = normalizeContext(request.getContext());
        context.setUserId(userId);
        request.setContext(context);
    }

    /** Redis is the only short-term conversation context source for the gateway. */
    private HistoryResolution resolveRedisHistory(Long userId, String sessionId) {
        if (userId == null || sessionId == null || sessionId.isBlank()) {
            return new HistoryResolution(new ArrayList<>(), "redis_unavailable");
        }
        return new HistoryResolution(toPythonHistory(readRedisMessages(redisKey(userId, sessionId))), "redis_cache");
    }

    private String redisKey(Long userId, String sessionId) {
        return "agent:chat:" + userId + ":" + sessionId.trim();
    }

    private List<JSONObject> readRedisMessages(String key) {
        List<JSONObject> messages = new ArrayList<>();
        try {
            Object raw = redisTemplate.opsForValue().get(key);
            if (!(raw instanceof List<?> rawMessages)) {
                return messages;
            }
            for (Object item : rawMessages) {
                if (item instanceof JSONObject json) {
                    messages.add(json);
                } else if (item instanceof Map<?, ?> map) {
                    JSONObject json = new JSONObject();
                    map.forEach((mapKey, value) -> json.put(String.valueOf(mapKey), value));
                    messages.add(json);
                }
            }
        } catch (Exception exception) {
            System.err.println("[AgentGatewayController] Redis上下文读取失败，本轮按空上下文继续: "
                    + safeErrorMessage(exception));
        }
        return messages;
    }

    private List<PythonChatMessage> toPythonHistory(List<JSONObject> messages) {
        List<PythonChatMessage> history = new ArrayList<>();
        for (JSONObject message : messages) {
            String role = message.getString("role");
            String content = message.getString("content");
            if (isSupportedRole(role) && content != null && !content.isBlank()) {
                history.add(new PythonChatMessage(role.trim().toLowerCase(), content.trim()));
            }
        }
        return history;
    }

    private void saveRedisHistory(Long userId, String sessionId, String userMessage, String assistantReply) {
        if (userId == null || sessionId == null || sessionId.isBlank()) {
            return;
        }
        String key = redisKey(userId, sessionId);
        List<JSONObject> messages = readRedisMessages(key);
        addRedisMessage(messages, "user", userMessage);
        addRedisMessage(messages, "assistant", cleanAssistantReplyForChatRecord(assistantReply));
        if (messages.size() > REDIS_CONTEXT_LIMIT) {
            messages = new ArrayList<>(messages.subList(messages.size() - REDIS_CONTEXT_LIMIT, messages.size()));
        }
        try {
            redisTemplate.opsForValue().set(key, messages, REDIS_CONTEXT_TTL_MINUTES, TimeUnit.MINUTES);
        } catch (Exception exception) {
            System.err.println("[AgentGatewayController] Redis上下文写入失败，不影响本轮回复: "
                    + safeErrorMessage(exception));
        }
    }

    private void addRedisMessage(List<JSONObject> messages, String role, String content) {
        if (content == null || content.isBlank()) {
            return;
        }
        JSONObject message = new JSONObject();
        message.put("role", role);
        message.put("content", content.trim());
        messages.add(message);
    }

    private boolean isSupportedRole(String role) {
        if (role == null) {
            return false;
        }
        String normalized = role.trim().toLowerCase();
        return "user".equals(normalized) || "assistant".equals(normalized);
    }

    private ChatRecordWriteResult persistChatRecords(
            Long userId,
            String redactedMessage,
            PythonOrchestratorResponse response
    ) {
        ChatRecordWriteResult result = new ChatRecordWriteResult();
        if (userId == null) {
            result.skipped = true;
            result.error = "context.user_id为空，无法写入chat_record";
            return result;
        }

        String emotion = resolveEmotionLabel(response);
        try {
            chatRecordService.saveMessage(
                    userId, "user", redactedMessage, emotion,
                    response == null ? null : response.getRequestId(),
                    response == null ? null : response.getSessionId()
            );
            result.savedSteps.add("chat_record:user");
        } catch (Exception exception) {
            result.error = "用户消息写入失败: " + safeErrorMessage(exception);
            return result;
        }

        if (response == null || !response.hasReply()) {
            result.error = "Python未返回可保存的回复";
            return result;
        }

        // chat_record 面向聊天展示，保存与前台一致的干净正文；RAG 引用、文档与
        // 分块标识由结构化分析结果和审计事件单独持久化，不混入用户可见回答。
        String assistantReply = cleanAssistantReplyForChatRecord(response.getReply());
        if (assistantReply == null || assistantReply.isBlank()) {
            result.error = "清理后的回复为空";
            return result;
        }

        try {
            chatRecordService.saveMessage(
                    userId, "assistant", assistantReply, null,
                    response.getRequestId(), response.getSessionId()
            );
            result.savedSteps.add("chat_record:assistant");
            result.saved = true;
        } catch (Exception exception) {
            result.error = "助手消息写入失败: " + safeErrorMessage(exception);
        }
        return result;
    }

    private String resolveEmotionLabel(PythonOrchestratorResponse response) {
        if (response == null || response.getEmotion() == null) {
            return null;
        }
        Object label = response.getEmotion().get("emotion");
        if (label == null || String.valueOf(label).isBlank()) {
            return null;
        }
        return String.valueOf(label).trim();
    }

    /**
     * RAG provenance is persisted by the dedicated RAG log. chat_record stores
     * only the user-facing answer so the session center never exposes internal
     * document/chunk identifiers.
     */
    private String cleanAssistantReplyForChatRecord(String reply) {
        if (reply == null) {
            return "";
        }
        String cleaned = reply
                .replaceAll("(?is)\\s*(?:参考(?:资料)?|引用|来源)\\s*[：:].*$", "")
                .replaceAll("(?i)\\s*/?(?:document_id|chunk_id|score)\\s*=\\s*[^;；,，\\s]+", "")
                .replaceAll(
                        "(?i)\\s*/?(student_psychology|stress_management|sleep_management|"
                                + "crisis_guidelines|school_resources)-(?:document-)?[\\p{Alnum}_-]{8,}",
                        ""
                )
                .replaceAll("(?i)\\s*/\\s*[\\p{Alnum}_-]*chunk-[\\p{Alnum}_-]+", "")
                .replaceAll("(?m)^\\s*(参考(?:资料)?|引用|来源)\\s*[：:]\\s*$", "")
                .replaceAll("[ \\t]+([。！？；;，,])", "$1")
                .replaceAll("[ \\t]+\\n", "\n")
                .replaceAll("\\n{3,}", "\n\n")
                .trim();
        return cleaned;
    }

    /**
     * Extract the user-facing answer from a Python/RAG response. Human-readable
     * reference titles are preserved; opaque document/chunk identifiers are
     * removed defensively and remain available only in structured RAG/audit data.
     */
    private String extractMainReply(String reply) {
        if (reply == null || reply.isBlank()) {
            return "";
        }

        return cleanAssistantReplyForChatRecord(reply);
    }

    private Map<String, Object> buildPersistence(
            Long userId,
            AgentAnalysisPersistenceService.PersistenceResult analysisResult,
            ChatRecordWriteResult chatResult,
            HistoryResolution historyResolution
    ) {
        boolean fullySaved = analysisResult.isSaved() && chatResult.saved;
        boolean partial = !fullySaved
                && (analysisResult.isPartial()
                || !analysisResult.getSavedSteps().isEmpty()
                || !chatResult.savedSteps.isEmpty());

        List<String> savedSteps = new ArrayList<>(analysisResult.getSavedSteps());
        savedSteps.addAll(chatResult.savedSteps);
        List<Object> failedSteps = new ArrayList<>(analysisResult.getFailedSteps());
        if (!chatResult.saved && !chatResult.skipped) {
            JSONObject chatFailure = new JSONObject();
            chatFailure.put("step", "chat_record");
            chatFailure.put("reason", chatResult.error);
            failedSteps.add(chatFailure);
        }

        Map<String, Object> persistence = new HashMap<>();
        persistence.put("saved", fullySaved);
        persistence.put("partial", partial);
        persistence.put("storage_owner", "java-backend");
        persistence.put("history_source", historyResolution.source);
        persistence.put("history_message_count", historyResolution.messages.size());
        persistence.put("chat_record_saved", chatResult.saved);
        persistence.put("chat_record_skipped", chatResult.skipped);
        persistence.put("saved_steps", savedSteps);
        persistence.put("failed_steps", failedSteps);
        if (chatResult.error != null) {
            persistence.put("chat_record_error", chatResult.error);
        }
        persistence.put(
                "reason",
                buildPersistenceReason(userId, analysisResult, chatResult, fullySaved, partial)
        );
        return persistence;
    }

    private String buildPersistenceReason(
            Long userId,
            AgentAnalysisPersistenceService.PersistenceResult analysisResult,
            ChatRecordWriteResult chatResult,
            boolean fullySaved,
            boolean partial
    ) {
        if (userId == null) {
            return "context.user_id为空，已跳过用户维度数据落库";
        }
        if (fullySaved) {
            return "聊天记录与智能体分析结果已由Java完整落库";
        }
        if (partial) {
            if (!chatResult.saved) {
                return "智能体结果已部分落库，但chat_record写入未完成，请查看failed_steps";
            }
            if (!analysisResult.isSaved()) {
                return "聊天记录已落库，但部分智能体分析结果写入失败，请查看failed_steps";
            }
        }
        return "聊天记录与智能体分析结果落库失败，请查看failed_steps";
    }

    private String resolveRedactedMessage(PythonOrchestratorResponse response, String fallback) {
        if (response == null || response.getSafety() == null) {
            return fallback;
        }
        Object redacted = response.getSafety().get("redacted_message");
        if (redacted == null || String.valueOf(redacted).isBlank()) {
            return fallback;
        }
        return String.valueOf(redacted);
    }

    private String safeErrorMessage(Exception exception) {
        String message = exception.getMessage();
        return message == null || message.isBlank()
                ? exception.getClass().getSimpleName()
                : message;
    }

    private static final class HistoryResolution {
        private final List<PythonChatMessage> messages;
        private final String source;

        private HistoryResolution(List<PythonChatMessage> messages, String source) {
            this.messages = messages;
            this.source = source;
        }
    }

    private static final class ChatRecordWriteResult {
        private boolean saved;
        private boolean skipped;
        private final List<String> savedSteps = new ArrayList<>();
        private String error;
    }
}
