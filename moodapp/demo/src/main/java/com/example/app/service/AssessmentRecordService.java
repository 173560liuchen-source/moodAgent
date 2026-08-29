package com.example.app.service;

import com.example.app.entity.AssessmentRecord;
import java.util.List;

public interface AssessmentRecordService {
    void saveRecord(AssessmentRecord record);

    List<AssessmentRecord> getRecentRecords(Long userId, int limit);

    void clearRecords(Long userId);
}
