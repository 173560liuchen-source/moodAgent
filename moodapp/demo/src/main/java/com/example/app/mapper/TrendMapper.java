package com.example.app.mapper;

import com.example.app.entity.PsychologicalTrend;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface TrendMapper {
    //插入数据
    @Insert("INSERT INTO psychological_trend(openid, anxiety_trend, stress_trend, emotion_trend, risk_trend, future_risk, suggestions, create_time)"+
        "VALUES(#{openId},#{anxietyTrend},#{stressTrend},#{emotionTrend},#{riskTrend},#{futureRisk},#{suggestions},#{createTime})")
    void insert(PsychologicalTrend trend);

    @Select(" SELECT * FROM psychological_trend WHERE openid = #{openId} ORDER BY create_time DESC LIMIT 1")
    PsychologicalTrend findLatest(String openId);
}
