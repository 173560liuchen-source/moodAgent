package com.example.app.mapper;


import com.example.app.entity.RiskReport;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface RiskReportMapper {

    @Insert("INSERT INTO risk_report (user_id, risk_level, risk_reasons, danger_signals, suggestions, need_center, conclusion, user_friendly_report, create_time) " +
            "VALUES (#{userId}, #{riskLevel}, #{riskReasons}, #{dangerSignals}, #{suggestions}, #{needCenter}, #{conclusion}, #{userFriendlyReport}, #{createTime})")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    void insert(RiskReport riskReport);

    @Select("SELECT * FROM risk_report WHERE user_id = #{userId} ORDER BY create_time DESC LIMIT 1")
    RiskReport findLatest(Long userId);

    @Select("SELECT * FROM risk_report WHERE user_id = #{userId} ORDER BY create_time DESC LIMIT #{limit}")
    List<RiskReport> findRecentByUserId(@Param("userId") Long userId, @Param("limit") int limit);
}
