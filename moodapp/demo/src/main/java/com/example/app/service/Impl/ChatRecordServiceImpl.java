package com.example.app.service.Impl;

import com.example.app.entity.ChatRecord;
import com.example.app.mapper.ChatRecordMapper;
import com.example.app.service.ChatRecordService;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class ChatRecordServiceImpl implements ChatRecordService {
    @Autowired
    private ChatRecordMapper chatRecordMapper;

    public ChatRecordServiceImpl() {
    }

    public void saveMessage(Long userId, String role, String content, String emotion) {
        saveMessage(userId, role, content, emotion, null, null);
    }

    @Override
    public void saveMessage(
            Long userId,
            String role,
            String content,
            String emotion,
            String requestId,
            String sessionId
    ) {
        ChatRecord record = new ChatRecord();
        record.setUserId(userId);
        record.setRole(role);
        record.setContent(content);
        record.setEmotion(emotion);
        record.setRequestId(requestId);
        record.setSessionId(sessionId);
        record.setCreateTime(LocalDateTime.now());
        this.chatRecordMapper.saveRecord(record);
    }

    public List<ChatRecord> getAllRecords(Long userId) {
        return this.chatRecordMapper.findByUserId(userId);
    }

    public List<Map<String, Object>> getRecordsGrouped(Long userId, int limit) {
        List<ChatRecord> records = this.chatRecordMapper.findRecentByUserId(userId, limit * 10);
        List<ChatRecord> sorted = new ArrayList(records);
        sorted.sort((a, b) -> {
            return a.getCreateTime().compareTo(b.getCreateTime());
        });
        List<Map<String, Object>> sessions = new ArrayList();
        Map<String, Object> currentSession = null;
        LocalDateTime lastTime = null;

        ChatRecord record;
        for(Iterator var8 = sorted.iterator(); var8.hasNext(); lastTime = record.getCreateTime()) {
            record = (ChatRecord)var8.next();
            if (currentSession == null) {
                currentSession = new HashMap();
                currentSession.put("time", record.getCreateTime());
                currentSession.put("messages", new ArrayList());
            }

            if (lastTime != null) {
                long minutesDiff = Duration.between(lastTime, record.getCreateTime()).toMinutes();
                if (minutesDiff > 5L) {
                    if (((List)currentSession.get("messages")).size() > 0) {
                        sessions.add(currentSession);
                    }

                    currentSession = new HashMap();
                    currentSession.put("time", record.getCreateTime());
                    currentSession.put("messages", new ArrayList());
                }
            }

            ((List)currentSession.get("messages")).add(record);
        }

        if (currentSession != null && ((List)currentSession.get("messages")).size() > 0) {
            sessions.add(currentSession);
        }

        return sessions;
    }

    public void deleteAllRecords(Long userId) {
        this.chatRecordMapper.deleteByUserId(userId);
    }
}
