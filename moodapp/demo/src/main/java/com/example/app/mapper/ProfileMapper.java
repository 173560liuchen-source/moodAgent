package com.example.app.mapper;

import com.example.app.entity.PsychologicalProfile;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface ProfileMapper {

    @Select("SELECT * FROM psychological_profile WHERE user_id = #{userId} ORDER BY create_time DESC LIMIT 1")
    PsychologicalProfile selectByUserId(Long userId);


    @Insert(" INSERT INTO psychological_profile( user_id, emotion_trait, stress_trait, anxiety_trait, risk_trait, summary, create_time)"
        +"VALUES(#{userId},#{emotionTrait},#{stressTrait},#{anxietyTrait},#{riskTrait},#{summary},#{createTime})")
    int insert(PsychologicalProfile profile);

    @Select("SELECT * FROM psychological_profile WHERE user_id = #{userId} ORDER BY create_time DESC LIMIT 1")
    PsychologicalProfile findLatest(Long userId);
}