package com.example.app.mapper;

import com.example.app.entity.CrisisEventLog;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface CrisisEventLogMapper {

    @Insert("INSERT INTO crisis_event_log " +
            "(user_id, request_id, level, self_harm, harm_to_others, immediacy, plan_present, tool_present, time_present, place_present, confidence, evidence, action, requires_human_review, hard_rule_triggered, rule_hits, decision_source, create_time) " +
            "VALUES " +
            "(#{userId}, #{requestId}, #{level}, #{selfHarm}, #{harmToOthers}, #{immediacy}, #{planPresent}, #{toolPresent}, #{timePresent}, #{placePresent}, #{confidence}, #{evidence}, #{action}, #{requiresHumanReview}, #{hardRuleTriggered}, #{ruleHits}, #{decisionSource}, #{createTime})")
    int insert(CrisisEventLog log);
}
