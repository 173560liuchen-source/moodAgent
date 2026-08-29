package com.example.app.entity;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@AllArgsConstructor
@NoArgsConstructor
@Data
public class SafetyEventLog {

    private Long id;
    private Long userId;
    private String requestId;
    private String decision;
    private String violations;
    private String piiTypes;
    private Boolean requiresHuman;
    private String evidence;
    private LocalDateTime createTime;
}
