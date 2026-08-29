package com.example.app.service;

import com.example.app.entity.ChatRecord;
import java.util.List;
import java.util.Map;

public interface ChatRecordService {
    void saveMessage(Long userId, String role, String content, String emotion);

    void saveMessage(Long userId, String role, String content, String emotion, String requestId, String sessionId);

    List<ChatRecord> getAllRecords(Long userId);


    List<Map<String, Object>> getRecordsGrouped(Long userId, int limit);

    void deleteAllRecords(Long userId);
}
