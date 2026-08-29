package com.example.app.dto;

import lombok.Data;

import java.util.List;

@Data
public class RecommendResponse {
    private Boolean success;
    private List<RecommendItem> recommendations;


}
