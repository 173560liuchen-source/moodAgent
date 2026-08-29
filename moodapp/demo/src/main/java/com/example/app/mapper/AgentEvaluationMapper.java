package com.example.app.mapper;

import com.example.app.entity.AgentEvaluation;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface AgentEvaluationMapper {

    @Insert("INSERT INTO agent_evaluation_record " +
            "(user_id, request_id, passed, score, action, issues, checked_dimensions, corrected_reply, final_reply, requires_human_review, rag_grounding_score, create_time) " +
            "VALUES " +
            "(#{userId}, #{requestId}, #{passed}, #{score}, #{action}, #{issues}, #{checkedDimensions}, #{correctedReply}, #{finalReply}, #{requiresHumanReview}, #{ragGroundingScore}, #{createTime})")
    int insert(AgentEvaluation evaluation);

    @Select("SELECT * FROM agent_evaluation_record WHERE user_id = #{userId} ORDER BY create_time DESC LIMIT 1")
    AgentEvaluation findLatestByUserId(Long userId);

    @Select("SELECT * FROM agent_evaluation_record WHERE request_id = #{requestId} LIMIT 1")
    AgentEvaluation findByRequestId(@Param("requestId") String requestId);
}
