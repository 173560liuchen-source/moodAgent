package com.example.app.entity;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@AllArgsConstructor
@NoArgsConstructor
@Data
public class ProfileItem {

    private Long id;

    private Long userId;

    private String category;

    private String value;

    private String evidence;

    private Double confidence;

    private String source;

    private Boolean editable;

    private Boolean deletable;

    private String sensitivity;

    private String status;

    private LocalDateTime createTime;

    private LocalDateTime updateTime;
}
