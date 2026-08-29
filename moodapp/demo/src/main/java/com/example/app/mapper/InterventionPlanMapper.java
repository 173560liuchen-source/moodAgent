package com.example.app.mapper;

import com.example.app.entity.InterventionPlan;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface InterventionPlanMapper {

    @Insert("INSERT INTO intervention_plan " +
            "(user_id, parent_plan_id, revision_no, decision_source, request_id, intervention_level, risk_level_source, strategy, actions, rationale, safety_constraints, profile_used, rag_citations_used, requires_human_review, confidence, create_time) " +
            "VALUES " +
            "(#{userId}, #{parentPlanId}, #{revisionNo}, #{decisionSource}, #{requestId}, #{interventionLevel}, #{riskLevelSource}, #{strategy}, #{actions}, #{rationale}, #{safetyConstraints}, #{profileUsed}, #{ragCitationsUsed}, #{requiresHumanReview}, #{confidence}, #{createTime})")
    int insert(InterventionPlan plan);

    @Select("SELECT * FROM intervention_plan WHERE user_id = #{userId} ORDER BY create_time DESC LIMIT 1")
    InterventionPlan findLatestByUserId(Long userId);

    @Select("SELECT * FROM intervention_plan WHERE id = #{planId} AND user_id = #{userId} LIMIT 1")
    InterventionPlan findByIdAndUserId(@Param("planId") Long planId, @Param("userId") Long userId);

    @Select("SELECT COALESCE(MAX(revision_no), -1) + 1 FROM intervention_plan WHERE user_id = #{userId}")
    int nextRevisionNo(@Param("userId") Long userId);
}
