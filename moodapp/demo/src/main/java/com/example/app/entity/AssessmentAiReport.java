package com.example.app.entity;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.io.Serializable;
import java.time.LocalDateTime;

@Data
@NoArgsConstructor
@AllArgsConstructor
@TableName("assessment_ai_report")
public class AssessmentAiReport implements Serializable {
    @TableId(
        type = IdType.AUTO
    )
    private Long id;
    private String openid;
    @TableField("user_id")
    private Long userId;
    private Integer score;
    private Integer standardScore;
    private String level;
    @TableField("emotional_analysis")
    private String emotionalAnalysis;
    @TableField("physical_symptoms")
    private String physicalSymptoms;
    @TableField("cognitive_status")
    private String cognitiveStatus;
    private String suggestions;
    private String summary;
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

}
