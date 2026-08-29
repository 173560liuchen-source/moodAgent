package com.example.app.service;

import com.example.app.entity.AssessmentAiReport;
import java.util.List;
import java.util.Map;

public interface AssessmentService {
    Map<String, Object> generateQuestions(int count);

    AssessmentAiReport generateAIReport(String openid, Integer score, String level, List<Integer> answers);

    List<AssessmentAiReport> getReportHistory(String openid);

    AssessmentAiReport getLatestReport(String openid);
}