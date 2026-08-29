package com.example.app.mapper;

import com.example.app.entity.ChatRecord;
import java.time.LocalDateTime;
import java.util.List;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface ChatRecordMapper {
    @Insert({"INSERT INTO chat_record (user_id, role, content, emotion, request_id, session_id, create_time) VALUES (#{userId}, #{role}, #{content}, #{emotion}, #{requestId}, #{sessionId}, #{createTime})"})
    int saveRecord(ChatRecord record);

    @Select({"SELECT * FROM chat_record WHERE user_id = #{userId} ORDER BY create_time DESC"})
    List<ChatRecord> findByUserId(Long userId);

    @Select({"SELECT * FROM chat_record WHERE user_id = #{userId} ORDER BY create_time DESC LIMIT #{limit}"})
    List<ChatRecord> findRecentByUserId(@Param("userId") Long userId, @Param("limit") int limit);

    @Delete({"DELETE FROM chat_record WHERE user_id = #{userId}"})
    int deleteByUserId(Long userId);

    @Delete({"DELETE FROM chat_record WHERE create_time < #{cutoffTime}"})
    int deleteOldRecords(LocalDateTime cutoffTime);
}
