package com.example.app.entity;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@AllArgsConstructor
@NoArgsConstructor
@Data
public class RagRetrievalLog {

    private Long id;
    private Long userId;
    private String requestId;
    private String queryText;
    private String rewrittenQuery;
    private String selectedCategories;
    private String citations;
    private Boolean hasEvidence;
    private String noEvidenceReason;
    private String retrievalStrategy;
    private Double confidence;
    private LocalDateTime createTime;
}
