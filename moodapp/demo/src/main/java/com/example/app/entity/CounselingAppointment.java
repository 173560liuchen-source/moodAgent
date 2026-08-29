package com.example.app.entity;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class CounselingAppointment {
    private Long id;
    private Long userId;
    private String name;
    private String phone;
    private String appointTime;
    private Integer status;
    private LocalDateTime createTime;
}