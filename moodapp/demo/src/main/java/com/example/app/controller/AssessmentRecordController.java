package com.example.app.controller;

import com.example.app.entity.AssessmentRecord;
import com.example.app.service.AssessmentRecordService;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import com.example.app.utils.AuthenticatedUser;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping({"/api/assessment"})
public class AssessmentRecordController {
    @Autowired
    private AssessmentRecordService assessmentRecordService;

    public AssessmentRecordController() {
    }

    @PostMapping({"/save"})
    public Map<String, Object> saveRecord(@RequestBody AssessmentRecord record, HttpServletRequest request) {
        Map<String, Object> result = new HashMap();

        try {
            System.out.println("收到测评记录保存请求: " + String.valueOf(record));
            record.setUserId(AuthenticatedUser.requireId(request));
            this.assessmentRecordService.saveRecord(record);
            result.put("code", 200);
            result.put("message", "保存成功");
        } catch (Exception var5) {
            var5.printStackTrace();
            result.put("code", 500);
            result.put("message", "保存失败: " + var5.getMessage());
        }

        return result;
    }

    @GetMapping({"/list"})
    public Map<String, Object> getRecordList(@RequestParam(required = false) Long userId, @RequestParam(defaultValue = "20") int limit, HttpServletRequest request) {
        userId = AuthenticatedUser.requireId(request);
        Map<String, Object> result = new HashMap();

        try {
            List<AssessmentRecord> records = this.assessmentRecordService.getRecentRecords(userId, limit);
            result.put("code", 200);
            result.put("data", records);
        } catch (Exception var6) {
            result.put("code", 500);
            result.put("message", "获取失败: " + var6.getMessage());
        }

        return result;
    }

    @PostMapping({"/clear"})
    public Map<String, Object> clearRecords(@RequestBody Map<String, String> params, HttpServletRequest request) {
        Map<String, Object> result = new HashMap();

        try {
            Long userId = AuthenticatedUser.requireId(request);
            this.assessmentRecordService.clearRecords(userId);
            result.put("code", 200);
            result.put("message", "清空成功");
        } catch (Exception var5) {
        }

        return result;
    }
}
