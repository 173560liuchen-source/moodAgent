package com.example.app.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@AllArgsConstructor
@NoArgsConstructor
public class MentalDTO {
    private Integer anxiety;
    private Integer stress;
    private Integer depression;
}
