package com.example.app.dto;

import lombok.Data;

@Data
public class RecommendRequest {
    private String openid;
    private String mood;
    private Integer assessmentScore;

}
