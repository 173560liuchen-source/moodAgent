package com.example.app.mapper;

import com.example.app.entity.InterventionActionFeedback;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface InterventionActionFeedbackMapper {
    @Insert("INSERT INTO intervention_action_feedback " +
            "(user_id, plan_id, action_id, execution_status, outcome_status, difficulty, feedback_note, source, create_time) " +
            "VALUES (#{userId}, #{planId}, #{actionId}, #{executionStatus}, #{outcomeStatus}, #{difficulty}, #{feedbackNote}, #{source}, #{createTime})")
    int insert(InterventionActionFeedback feedback);

    @Select("SELECT * FROM intervention_action_feedback WHERE user_id = #{userId} ORDER BY create_time DESC LIMIT #{limit}")
    List<InterventionActionFeedback> findRecentByUserId(@Param("userId") Long userId, @Param("limit") int limit);

    @Select("SELECT * FROM intervention_action_feedback WHERE user_id = #{userId} AND plan_id = #{planId} ORDER BY create_time DESC LIMIT #{limit}")
    List<InterventionActionFeedback> findRecentByPlanIdAndUserId(
            @Param("planId") Long planId, @Param("userId") Long userId, @Param("limit") int limit);
}
