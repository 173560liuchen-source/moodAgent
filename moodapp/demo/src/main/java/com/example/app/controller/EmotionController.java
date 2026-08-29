package com.example.app.controller;

import com.example.app.service.EmotionService;
import jakarta.servlet.http.HttpServletRequest;
import java.util.HashMap;
import java.util.Map;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping({"/emotion"})
public class EmotionController {
    @Autowired
    private EmotionService emotionService;

    public EmotionController() {
    }

    @PostMapping({"/analyze"})
    public Map<String, Object> analyzeEmotion(@RequestParam("image") MultipartFile file, @RequestParam(required = false) String openid, HttpServletRequest request) {
        Map<String, Object> result = new HashMap();

        try {
            if (file != null && !file.isEmpty()) {
                Map<String, Object> emotionData = this.emotionService.analyzeEmotion(file.getBytes());
                result.put("success", true);
                result.put("emotion", emotionData);
                result.put("message", "分析成功");
                return result;
            } else {
                result.put("success", false);
                result.put("message", "图片不能为空");
                return result;
            }
        } catch (Exception var6) {
            var6.printStackTrace();
            result.put("success", false);
            result.put("message", "分析失败: " + var6.getMessage());
            return result;
        }
    }

    @GetMapping({"/test"})
    public Map<String, Object> test() {
        Map<String, Object> result = new HashMap();
        result.put("success", true);
        result.put("message", "情绪分析服务正常");
        return result;
    }
}
