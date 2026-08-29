package com.example.app.controller;

import com.example.app.dto.ApiResponse;
import com.example.app.dto.python.PythonAgentContext;
import com.example.app.dto.python.PythonOrchestratorRequest;
import com.example.app.dto.python.PythonOrchestratorResponse;
import com.example.app.mapper.AgentAuditEventMapper;
import com.example.app.mapper.InterventionActionFeedbackMapper;
import com.example.app.mapper.InterventionPlanMapper;
import com.example.app.mapper.MentalStateMapper;
import com.example.app.mapper.ProfileMapper;
import com.example.app.service.ChatRecordService;
import com.example.app.service.Impl.AgentAnalysisPersistenceService;
import com.example.app.service.Impl.PythonOrchestratorService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AgentGatewayWorkflowTests {

    private AgentGatewayController controller;
    private PythonOrchestratorService python;
    private AgentAnalysisPersistenceService persistence;
    private ChatRecordService chatRecords;
    private RedisTemplate<String, Object> redis;
    private ValueOperations<String, Object> redisValues;

    @BeforeEach
    void setUp() {
        controller = new AgentGatewayController();
        python = mock(PythonOrchestratorService.class);
        persistence = mock(AgentAnalysisPersistenceService.class);
        chatRecords = mock(ChatRecordService.class);
        redis = mock(RedisTemplate.class);
        redisValues = mock(ValueOperations.class);
        ReflectionTestUtils.setField(controller, "pythonOrchestratorService", python);
        ReflectionTestUtils.setField(controller, "agentAnalysisPersistenceService", persistence);
        ReflectionTestUtils.setField(controller, "chatRecordService", chatRecords);
        ReflectionTestUtils.setField(controller, "redisTemplate", redis);
        ReflectionTestUtils.setField(controller, "mentalStateMapper", mock(MentalStateMapper.class));
        ReflectionTestUtils.setField(controller, "agentAuditEventMapper", mock(AgentAuditEventMapper.class));
        ReflectionTestUtils.setField(controller, "interventionPlanMapper", mock(InterventionPlanMapper.class));
        ReflectionTestUtils.setField(controller, "interventionActionFeedbackMapper", mock(InterventionActionFeedbackMapper.class));
        ReflectionTestUtils.setField(controller, "profileMapper", mock(ProfileMapper.class));
        when(redis.opsForValue()).thenReturn(redisValues);
        when(redisValues.get(any())).thenReturn(List.of());
        when(persistence.persist(anyLong(), any(), any(), any(), anyLong()))
                .thenReturn(new AgentAnalysisPersistenceService.PersistenceResult());
    }

    @Test
    void chatRiskRagInterventionResultIsPersistedAsOneWorkflow() {
        PythonOrchestratorResponse pythonResult = fullWorkflowResult();
        when(python.orchestrate(anyLong(), any(), any(), any(), any(), any())).thenReturn(pythonResult);

        ApiResponse<PythonOrchestratorResponse> response = controller.orchestrate(request(), authenticatedRequest());

        assertThat(response.getCode()).isEqualTo(200);
        assertThat(response.getData().getReply()).isEqualTo("先做三次缓慢呼吸。");
        assertThat(response.getData().getRag()).containsKey("citations");
        assertThat(response.getData().getIntervention()).containsEntry("strategy", "breathing");
        verify(python).orchestrate(anyLong(), any(), any(), any(), any(), any());
        verify(chatRecords).saveMessage(7L, "user", "我不知道怎么办", "stressed", "workflow-1", "workflow-session");
        verify(chatRecords).saveMessage(7L, "assistant", "先做三次缓慢呼吸。", null, "workflow-1", "workflow-session");
        verify(redisValues, times(2)).get("agent:chat:7:workflow-session");
        verify(redisValues).set(eq("agent:chat:7:workflow-session"), any(), eq(30L), any());
        verify(chatRecords, never()).getAllRecords(anyLong());
        verify(persistence).persist(eq(7L), eq(pythonResult), eq("我不知道怎么办"), eq("我不知道怎么办"), anyLong());
    }

    @Test
    void databaseFailureIsReturnedAsAuditablePartialPersistenceInsteadOfBreakingReply() {
        when(python.orchestrate(anyLong(), any(), any(), any(), any(), any())).thenReturn(fullWorkflowResult());
        doThrow(new IllegalStateException("database unavailable"))
                .when(chatRecords).saveMessage(7L, "user", "我不知道怎么办", "stressed", "workflow-1", "workflow-session");

        ApiResponse<PythonOrchestratorResponse> response = controller.orchestrate(request(), authenticatedRequest());

        assertThat(response.getCode()).isEqualTo(200);
        assertThat(response.getData().getReply()).contains("缓慢呼吸");
        assertThat(response.getData().getPersistence()).containsEntry("saved", false);
        assertThat((List<?>) response.getData().getPersistence().get("failed_steps"))
                .anySatisfy(item -> assertThat(((Map<?, ?>) item).get("step")).isEqualTo("chat_record"));
        verify(persistence).persist(eq(7L), eq(response.getData()), eq("我不知道怎么办"), eq("我不知道怎么办"), anyLong());
    }

    @Test
    void streamEndpointEmitsOnlyTheFinalEvaluatedReply() throws Exception {
        PythonOrchestratorResponse pythonResult = fullWorkflowResult();
        when(python.orchestrate(
                anyLong(), any(), any(), any(), any(), any()
        )).thenReturn(pythonResult);
        MockHttpServletResponse servletResponse = new MockHttpServletResponse();
        StreamingResponseBody body = controller.orchestrateStream(
                request(), servletResponse, authenticatedRequest()
        );
        ByteArrayOutputStream output = new ByteArrayOutputStream();

        body.writeTo(output);

        String events = output.toString(StandardCharsets.UTF_8);
        assertThat(events).contains("先做三次缓慢呼吸。");
        assertThat(events).doesNotContain("参考资料");
        verify(python).orchestrate(anyLong(), any(), any(), any(), any(), any());
    }

    private PythonOrchestratorRequest request() {
        PythonAgentContext context = new PythonAgentContext("workflow-1", 7L, "workflow-session", new HashMap<>());
        return new PythonOrchestratorRequest("我不知道怎么办", List.of(), context);
    }

    private MockHttpServletRequest authenticatedRequest() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.setAttribute("userId", 7L);
        return request;
    }

    private PythonOrchestratorResponse fullWorkflowResult() {
        PythonOrchestratorResponse result = new PythonOrchestratorResponse();
        result.setRequestId("workflow-1");
        result.setSessionId("workflow-session");
        result.setReply("先做三次缓慢呼吸。\n\n参考资料：[1]《压力管理指南》");
        result.setEmotion(Map.of("emotion", "stressed"));
        result.setCrisis(Map.of("level", "low"));
        result.setRisk(Map.of("level", "low"));
        result.setRag(Map.of("citations", List.of(Map.of("chunk_id", "chunk-1"))));
        result.setIntervention(Map.of("strategy", "breathing"));
        return result;
    }
}
