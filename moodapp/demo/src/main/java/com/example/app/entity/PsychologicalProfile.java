package com.example.app.entity;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@AllArgsConstructor
@NoArgsConstructor
@Data
public class PsychologicalProfile {

    private Long id;

    private Long userId;

    private String emotionTrait;

    private String stressTrait;

    private String anxietyTrait;

    private String riskTrait;

    private String summary;

    private LocalDateTime createTime;
}