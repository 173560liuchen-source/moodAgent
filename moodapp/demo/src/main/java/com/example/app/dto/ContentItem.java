package com.example.app.dto;

import lombok.Data;

@Data
public class ContentItem {
    private Integer id;
    private String title;
    private String duration;
    private String cover;
    private String url;
    private String type;

}
