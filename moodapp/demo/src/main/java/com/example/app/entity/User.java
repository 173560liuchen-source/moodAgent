package com.example.app.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.util.Date;

@AllArgsConstructor
@NoArgsConstructor
@Data
@TableName("user")
public class User {
    @TableId(
            type = IdType.AUTO
    )
    private Long id;
    private String openid;
    @TableField("password_hash")
    private String passwordHash;
    private String nickname;
    private String avatar;
    private Integer gender;
    private String phone;
    private Integer age;
    private String mood;
    @TableField("last_assessment_score")
    private Integer lastAssessmentScore;
    @TableField("preferred_categories")
    private String preferredCategories;
    @TableField("create_time")
    private LocalDateTime createTime;
    @TableField("update_time")
    private Date updateTime;
}
