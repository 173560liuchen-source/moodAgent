package com.example.app.mapper;

import com.example.app.entity.InterventionFollowUp;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface InterventionFollowUpMapper {
    @Insert("INSERT INTO intervention_follow_up " +
            "(user_id, plan_id, request_id, adjusted_plan_request_id, feedback_text, adherence, effectiveness, decision, emotion_change, risk_change, evidence, adjustment_reason, confidence, create_time) " +
            "VALUES (#{userId}, #{planId}, #{requestId}, #{adjustedPlanRequestId}, #{feedbackText}, #{adherence}, #{effectiveness}, #{decision}, #{emotionChange}, #{riskChange}, #{evidence}, #{adjustmentReason}, #{confidence}, #{createTime})")
    int insert(InterventionFollowUp record);

    @Select("SELECT * FROM intervention_follow_up WHERE user_id = #{userId} ORDER BY create_time DESC LIMIT #{limit}")
    List<InterventionFollowUp> findRecentByUserId(@Param("userId") Long userId, @Param("limit") int limit);
}
