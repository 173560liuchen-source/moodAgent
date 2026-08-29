package com.example.app.controller;

import com.example.app.entity.ChatRecord;
import com.example.app.service.ChatRecordService;
import jakarta.annotation.Resource;
import jakarta.servlet.http.HttpServletRequest;
import com.example.app.utils.AuthenticatedUser;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;


import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping({"/chat"})
public class ChatController {

    @Resource
    private ChatRecordService chatRecordService;

    //获取最近的聊天记录
    @GetMapping({"/list"})
    public Map<String, Object> getChatList(@RequestParam(required = false) Long userId, @RequestParam(defaultValue = "20") int limit, HttpServletRequest request) {
        userId = AuthenticatedUser.requireId(request);
        Map<String, Object> result = new HashMap();

        try {
            List<Map<String, Object>> sessions = this.chatRecordService.getRecordsGrouped(userId, limit);
            List<Map<String, Object>> data = new ArrayList();

            HashMap item;
            for(Iterator var7 = sessions.iterator(); var7.hasNext(); data.add(item)) {
                Map<String, Object> session = (Map)var7.next();
                item = new HashMap();
                item.put("time", session.get("time"));
                List<ChatRecord> msgs = (List)session.get("messages");
                List<Map<String, Object>> msgList = new ArrayList();
                if (msgs != null && !msgs.isEmpty()) {
                    Iterator var12 = msgs.iterator();

                    while(var12.hasNext()) {
                        ChatRecord msg = (ChatRecord)var12.next();
                        Map<String, Object> msgMap = new HashMap();
                        msgMap.put("id", msg.getId());
                        msgMap.put("role", msg.getRole());
                        msgMap.put("content", msg.getContent());
                        msgMap.put("emotion", msg.getEmotion());
                        msgMap.put("createTime", msg.getCreateTime());
                        msgList.add(msgMap);
                    }
                }

                item.put("messages", msgList);
                if (!msgList.isEmpty()) {
                    int messageCount = msgList.size();
                    String preview = "";
                    Iterator var19 = msgList.iterator();

                    while(var19.hasNext()) {
                        Map<String, Object> msg = (Map)var19.next();
                        if ("user".equals(msg.get("role")) && preview.isEmpty()) {
                            preview = (String)msg.get("content");
                        }
                    }

                    item.put("messageCount", messageCount);
                    item.put("preview", preview != null && preview.length() > 50 ? preview.substring(0, 50) + "..." : (preview != null ? preview : ""));
                }
            }

            result.put("code", 200);
            result.put("data", data);
        } catch (Exception var16) {
            result.put("code", 500);
            result.put("message", "获取失败: " + var16.getMessage());
        }

        return result;
    }

    @GetMapping({"/all"})
    public Map<String, Object> getAllRecords(@RequestParam(required = false) Long userId, HttpServletRequest request) {
        userId = AuthenticatedUser.requireId(request);
        Map<String, Object> result = new HashMap();

        try {
            List<ChatRecord> records = this.chatRecordService.getAllRecords(userId);
            result.put("code", 200);
            result.put("data", records);
        } catch (Exception var5) {
            result.put("code", 500);
            result.put("message", "获取失败: " + var5.getMessage());
        }

        return result;
    }

    @PostMapping({"/save"})
    public Map<String, Object> saveRecord(@RequestBody Map<String, Object> params, HttpServletRequest request) {
        Map<String, Object> result = new HashMap();

        try {
            Long userId = AuthenticatedUser.requireId(request);
            String role = params.get("role").toString();
            String content = params.get("content").toString();
            String emotion = params.get("emotion") != null ? params.get("emotion").toString() : null;
            this.chatRecordService.saveMessage(userId, role, content, emotion);
            result.put("code", 200);
            result.put("message", "保存成功");
        } catch (Exception var7) {
            result.put("code", 500);
            result.put("message", "保存失败: " + var7.getMessage());
        }

        return result;
    }

    @PostMapping({"/clear"})
    public Map<String, Object> clearAll(@RequestBody Map<String, Object> params, HttpServletRequest request) {
        Map<String, Object> result = new HashMap();

        try {
            Long userId = AuthenticatedUser.requireId(request);
            this.chatRecordService.deleteAllRecords(userId);
            result.put("code", 200);
            result.put("message", "已清空全部记录");
        } catch (Exception var4) {
            result.put("code", 500);
            result.put("message", "清空失败: " + var4.getMessage());
        }

        return result;
    }

}
