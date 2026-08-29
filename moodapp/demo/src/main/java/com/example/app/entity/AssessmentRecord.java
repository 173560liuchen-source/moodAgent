package com.example.app.entity;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Data
@AllArgsConstructor
@NoArgsConstructor
public class AssessmentRecord {
    private Long id;
    private Long userId;
    private String scaleType;
    private Integer score;
    private String result;
    private String suggestion;
    private LocalDateTime createTime;
}