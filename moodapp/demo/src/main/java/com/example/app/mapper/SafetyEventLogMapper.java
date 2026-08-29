package com.example.app.mapper;

import com.example.app.entity.SafetyEventLog;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface SafetyEventLogMapper {

    @Insert("INSERT INTO safety_event_log " +
            "(user_id, request_id, decision, violations, pii_types, requires_human, evidence, create_time) " +
            "VALUES " +
            "(#{userId}, #{requestId}, #{decision}, #{violations}, #{piiTypes}, #{requiresHuman}, #{evidence}, #{createTime})")
    int insert(SafetyEventLog log);
}
