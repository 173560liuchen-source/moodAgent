package com.example.app.Task;

import com.example.app.mapper.AssessmentRecordMapper;
import java.time.LocalDateTime;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class AssessmentRecordCleanupTask {
    @Autowired
    private AssessmentRecordMapper assessmentRecordMapper;

    public AssessmentRecordCleanupTask() {
    }

    @Scheduled(
        cron = "0 0 2 * * ?"
    )
    public void cleanupOldRecords() {
        try {
            LocalDateTime cutoffTime = LocalDateTime.now().minusDays(1L);
            int deletedCount = this.assessmentRecordMapper.deleteOldRecords(cutoffTime);
            System.out.println("【定时清理】删除了 " + deletedCount + " 条1天前的测评记录");
        } catch (Exception var3) {
            System.err.println("【定时清理】执行失败: " + var3.getMessage());
        }

    }

    @Scheduled(
        cron = "0 0 3 ? * SUN"
    )
    public void deepCleanup() {
        try {
            LocalDateTime cutoffTime = LocalDateTime.now().minusDays(3L);
            int deletedCount = this.assessmentRecordMapper.deleteOldRecords(cutoffTime);
            System.out.println("【深度清理】删除了 " + deletedCount + " 条3天前的测评记录");
        } catch (Exception var3) {
            System.err.println("【深度清理】执行失败: " + var3.getMessage());
        }

    }
}
