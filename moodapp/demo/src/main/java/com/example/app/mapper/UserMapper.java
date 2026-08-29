package com.example.app.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.example.app.entity.User;
import java.time.LocalDateTime;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface UserMapper extends BaseMapper<User> {
    @Select({"select * from user where openid = #{openid}"})
    User selectByOpenid(String openid);

    @Insert({"INSERT INTO user (openid, nickname, avatar, gender, mood, create_time) VALUES (#{openid}, #{nickname}, #{avatar}, #{gender}, #{mood}, NOW())"})
    @Options(useGeneratedKeys = true, keyProperty = "id")
    int insert(User user);

    @Insert({"INSERT INTO user (openid, password_hash, nickname, avatar, gender, mood, create_time) " +
            "VALUES (#{openid}, #{passwordHash}, #{nickname}, #{avatar}, #{gender}, #{mood}, NOW())"})
    @Options(useGeneratedKeys = true, keyProperty = "id")
    int insertAccountUser(User user);

    @Update({"UPDATE user SET nickname = #{nickname}, avatar = #{avatar}, gender = #{gender}, mood = #{mood}, update_time = NOW() WHERE id = #{id}"})
    int update(User user);

    @Update({"UPDATE user SET mood = #{mood}, update_time = NOW() WHERE id = #{id}"})
    int updateMood(@Param("id") Long id, @Param("mood") String mood);

    @Update({"UPDATE user SET last_assessment_score = #{score}, update_time = NOW() WHERE openid = #{openid}"})
    int updateAssessmentScore(@Param("openid") String openid, @Param("score") Integer score);

    @Select({"SELECT * FROM user WHERE id = #{id}"})
    User findById(Long id);

    @Select({"SELECT * FROM user WHERE token = #{token} AND token_expire_time > NOW()"})
    User findByToken(String token);

    @Update({"UPDATE user SET token = #{token}, token_expire_time = #{tokenExpireTime}, update_time = NOW() WHERE openid = #{openid}"})
    int updateToken(@Param("openid") String openid, @Param("token") String token, @Param("tokenExpireTime") LocalDateTime tokenExpireTime);

    @Update({"UPDATE user SET token = NULL, token_expire_time = NULL, update_time = NOW() WHERE openid = #{openid}"})
    int clearToken(String openid);
}
