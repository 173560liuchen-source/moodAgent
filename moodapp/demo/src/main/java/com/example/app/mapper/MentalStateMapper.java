package com.example.app.mapper;

import com.example.app.entity.MentalState;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface MentalStateMapper {

    @Insert("insert into mental_state " +
            "(user_id, anxiety, stress, depression, emotion_risk, trend_risk, risk_score, create_time) " +
            "values (#{userId}, #{anxiety}, #{stress}, #{depression}, " +
            "#{emotionRisk}, #{trendRisk}, #{riskScore}, #{createTime})")
    void insert(MentalState mentalState);

    @Select("select * from mental_state where user_id = #{userId} order by create_time desc limit 1")
    MentalState findLatestByUserId(Long userId);

    @Select("select * from mental_state where user_id = #{userId} order by create_time asc limit #{limit}")
    List<MentalState> findRecentByUserId(@Param("userId") Long userId,@Param("limit") int limit);

    @Select("select * from mental_state where user_id = #{userId} order by create_time desc limit #{limit}")
    List<MentalState> findLatestHistory(@Param("userId") Long userId, @Param("limit") int limit);
}
