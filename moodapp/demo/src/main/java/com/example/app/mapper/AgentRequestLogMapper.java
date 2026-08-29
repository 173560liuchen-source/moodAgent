package com.example.app.mapper;

import com.example.app.entity.AgentRequestLog;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface AgentRequestLogMapper {

    @Insert("INSERT INTO agent_request_log " +
            "(user_id, request_id, session_id, message_hash, redacted_message_hash, agent_entry, workflow_engine, workflow_version, model_name, status, error_code, latency_ms, create_time) " +
            "VALUES " +
            "(#{userId}, #{requestId}, #{sessionId}, #{messageHash}, #{redactedMessageHash}, #{agentEntry}, #{workflowEngine}, #{workflowVersion}, #{modelName}, #{status}, #{errorCode}, #{latencyMs}, #{createTime})")
    int insert(AgentRequestLog log);

    @Select("SELECT * FROM agent_request_log WHERE user_id = #{userId} ORDER BY create_time DESC LIMIT #{limit}")
    List<AgentRequestLog> findRecentByUserId(@Param("userId") Long userId, @Param("limit") int limit);

    @Select("SELECT * FROM agent_request_log WHERE request_id = #{requestId} LIMIT 1")
    AgentRequestLog findByRequestId(@Param("requestId") String requestId);
}
