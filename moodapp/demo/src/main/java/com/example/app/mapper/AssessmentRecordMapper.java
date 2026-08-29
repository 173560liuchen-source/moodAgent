package com.example.app.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.example.app.entity.AssessmentRecord;
import java.time.LocalDateTime;
import java.util.List;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface AssessmentRecordMapper extends BaseMapper<AssessmentRecord> {
    @Insert({"INSERT INTO assessment_record (user_id, scale_type, score, result, suggestion) VALUES (#{userId}, #{scaleType}, #{score}, #{result}, #{suggestion})"})
    int saveRecord(AssessmentRecord record);

    @Select({"SELECT * FROM assessment_record WHERE user_id = #{userId} ORDER BY create_time DESC LIMIT #{limit}"})
    List<AssessmentRecord> findRecentByUserId(@Param("userId") Long userId, @Param("limit") int limit);

    @Delete({"DELETE FROM assessment_record WHERE user_id = #{userId}"})
    void deleteByUserId(Long userId);

    @Delete({"DELETE FROM assessment_record WHERE create_time < #{cutoffTime}"})
    int deleteOldRecords(LocalDateTime cutoffTime);
}