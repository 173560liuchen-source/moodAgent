package com.example.app.mapper;

import com.example.app.entity.AgentAuditEvent;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface AgentAuditEventMapper {

    @Insert("INSERT INTO agent_audit_log " +
            "(user_id, request_id, session_id, agent_trace, trace_events, safety_result, crisis_result, emotion_result, rag_result, profile_result, intervention_result, evaluator_result, audit_result, model_name, workflow_engine, workflow_version, latency_ms, create_time) " +
            "VALUES " +
            "(#{userId}, #{requestId}, #{sessionId}, #{agentTrace}, #{traceEvents}, #{safetyResult}, #{crisisResult}, #{emotionResult}, #{ragResult}, #{profileResult}, #{interventionResult}, #{evaluatorResult}, #{auditResult}, #{modelName}, #{workflowEngine}, #{workflowVersion}, #{latencyMs}, #{createTime})")
    int insert(AgentAuditEvent event);

    @Select("SELECT * FROM agent_audit_log WHERE user_id = #{userId} ORDER BY create_time DESC LIMIT #{limit}")
    List<AgentAuditEvent> findRecentByUserId(@Param("userId") Long userId, @Param("limit") int limit);

    @Select("SELECT * FROM agent_audit_log ORDER BY create_time DESC LIMIT #{limit}")
    List<AgentAuditEvent> findRecent(@Param("limit") int limit);

    @Select("SELECT * FROM agent_audit_log WHERE request_id = #{requestId} LIMIT 1")
    AgentAuditEvent findByRequestId(@Param("requestId") String requestId);

    @Select("SELECT * FROM agent_audit_log " +
            "WHERE user_id = #{userId} AND session_id = #{sessionId} " +
            "ORDER BY create_time DESC LIMIT 1")
    AgentAuditEvent findLatestByUserAndSession(
            @Param("userId") Long userId,
            @Param("sessionId") String sessionId
    );
}
