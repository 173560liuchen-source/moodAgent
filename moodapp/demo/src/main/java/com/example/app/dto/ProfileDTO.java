package com.example.app.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@AllArgsConstructor
@NoArgsConstructor
@Data
public class ProfileDTO {

    private String emotionTrait;

    private String stressTrait;

    private String anxietyTrait;

    private String riskTrait;

    private String summary;
}