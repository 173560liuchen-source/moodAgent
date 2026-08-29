package com.example.app.service.Impl;

import com.example.app.entity.AssessmentRecord;
import com.example.app.mapper.AssessmentRecordMapper;
import com.example.app.service.AssessmentRecordService;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class AssessmentRecordServiceImpl implements AssessmentRecordService {
    @Autowired
    private AssessmentRecordMapper assessmentRecordMapper;

    public AssessmentRecordServiceImpl() {
    }

    public void saveRecord(AssessmentRecord record) {
        this.assessmentRecordMapper.saveRecord(record);
    }

    public List<AssessmentRecord> getRecentRecords(Long userId, int limit) {
        return this.assessmentRecordMapper.findRecentByUserId(userId, limit);
    }

    public void clearRecords(Long userId) {
        this.assessmentRecordMapper.deleteByUserId(userId);
    }
}
