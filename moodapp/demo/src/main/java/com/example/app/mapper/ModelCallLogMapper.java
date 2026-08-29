package com.example.app.mapper;

import com.example.app.entity.ModelCallLog;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface ModelCallLogMapper {

    @Insert("INSERT INTO model_call_log " +
            "(user_id, request_id, agent_name, model_name, prompt_version, input_tokens, output_tokens, total_tokens, latency_ms, success, error_code, create_time) " +
            "VALUES " +
            "(#{userId}, #{requestId}, #{agentName}, #{modelName}, #{promptVersion}, #{inputTokens}, #{outputTokens}, #{totalTokens}, #{latencyMs}, #{success}, #{errorCode}, #{createTime})")
    int insert(ModelCallLog log);
}
