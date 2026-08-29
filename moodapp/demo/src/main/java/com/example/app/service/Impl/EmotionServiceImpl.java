package com.example.app.service.Impl;

//视觉分析模块

import cn.hutool.http.HttpRequest;
import cn.hutool.json.JSONArray;
import cn.hutool.json.JSONObject;
import com.example.app.service.EmotionService;
import java.util.Base64;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class EmotionServiceImpl implements EmotionService {

    @Value("${aliyun.qwen.api-key}")
    private String apiKey;

    private static final Map<String, String> EMOTION_MAP = new LinkedHashMap();
    private static final Map<String, String> EMOTION_SUGGESTIONS = new LinkedHashMap();

    public EmotionServiceImpl() {
    }

    public Map<String, Object> analyzeEmotion(byte[] imageBytes) {
        try {
            String imageBase64 = Base64.getEncoder().encodeToString(imageBytes);
            return this.analyzeWithVisionModel(imageBase64);
        } catch (Exception var3) {
            var3.printStackTrace();
            System.out.println("情绪分析失败，使用默认结果: " + var3.getMessage());
            return this.getDefaultEmotionResult();
        }
    }

    private Map<String, Object> analyzeWithVisionModel(String imageBase64) {
        try {
            String prompt = "请分析这张图片中人物的表情和情绪状态。\n请用JSON格式返回分析结果：\n{\n  \"emotion\": \"主要情绪（开心/平静/惊讶/悲伤/愤怒/恐惧/厌恶）\",\n  \"confidence\": 置信度(0-100),\n  \"happiness\": 开心程度(0-100),\n  \"sadness\": 悲伤程度(0-100),\n  \"anger\": 愤怒程度(0-100),\n  \"fear\": 恐惧程度(0-100),\n  \"surprise\": 惊讶程度(0-100),\n  \"reason\": \"简要说明分析理由\"\n}\n只返回JSON，不要其他内容。";
            JSONArray contentArray = new JSONArray();
            JSONObject textContent = new JSONObject();
            textContent.set("type", "text");
            textContent.set("text", prompt);
            contentArray.add(textContent);
            JSONObject imageUrlObj = new JSONObject();
            imageUrlObj.set("url", "data:image/jpeg;base64," + imageBase64);
            JSONObject imageContent = new JSONObject();
            imageContent.set("type", "image_url");
            imageContent.set("image_url", imageUrlObj);
            contentArray.add(imageContent);
            JSONObject message = new JSONObject();
            message.set("role", "user");
            message.set("content", contentArray);
            JSONArray messages = new JSONArray();
            messages.add(message);
            JSONObject body = new JSONObject();
            body.set("model", "qwen-vl-plus");
            body.set("messages", messages);
            String response = ((HttpRequest)((HttpRequest)HttpRequest.post("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions").header("Authorization", "Bearer " + this.apiKey)).header("Content-Type", "application/json")).body(body.toString()).timeout(30000).execute().body();
            System.out.println("视觉分析响应: " + response);
            JSONObject jsonResponse = new JSONObject(response);
            JSONArray choices = jsonResponse.getJSONArray("choices");
            if (choices != null && !choices.isEmpty()) {
                JSONObject messageObj = choices.getJSONObject(0).getJSONObject("message");
                String content = messageObj.getStr("content");
                return this.parseVisionResponse(content);
            }
        } catch (Exception var15) {
            System.out.println("视觉分析出错: " + var15.getMessage());
            var15.printStackTrace();
        }

        return this.getDefaultEmotionResult();
    }

    private Map<String, Object> parseVisionResponse(String content) {
        Map<String, Object> result = new HashMap();

        try {
            String jsonStr = content.trim();
            if (jsonStr.contains("```json")) {
                jsonStr = jsonStr.substring(jsonStr.indexOf("```json") + 7);
                jsonStr = jsonStr.substring(0, jsonStr.indexOf("```"));
            }

            jsonStr = jsonStr.trim();
            JSONObject json = new JSONObject(jsonStr);
            String emotion = json.getStr("emotion");
            int confidence = json.getInt("confidence", 85);
            int happiness = json.getInt("happiness", 50);
            int sadness = json.getInt("sadness", 20);
            int anger = json.getInt("anger", 10);
            int fear = json.getInt("fear", 10);
            int surprise = json.getInt("surprise", 10);
            result.put("emotion", emotion);
            result.put("confidence", confidence);
            result.put("happiness", happiness);
            result.put("sadness", sadness);
            result.put("anger", anger);
            result.put("fear", fear);
            result.put("surprise", surprise);
            result.put("arousal", Math.min(100, happiness + surprise / 2));
            result.put("dominance", Math.min(100, happiness + 30));
            result.put("anxiety", Math.max(anger, fear));
            result.put("depression", sadness);
            result.put("suggestion", EMOTION_SUGGESTIONS.getOrDefault(emotion, (String)EMOTION_SUGGESTIONS.get("平静")));
            result.put("reason", json.getStr("reason"));
            return result;
        } catch (Exception var12) {
            System.out.println("解析视觉响应失败: " + var12.getMessage());
            var12.printStackTrace();
            return this.getDefaultEmotionResult();
        }
    }

    private Map<String, Object> getDefaultEmotionResult() {
        Map<String, Object> result = new HashMap();
        result.put("emotion", "平静");
        result.put("confidence", 85);
        result.put("happiness", 50);
        result.put("sadness", 20);
        result.put("anger", 10);
        result.put("fear", 10);
        result.put("surprise", 10);
        result.put("arousal", 55);
        result.put("dominance", 60);
        result.put("anxiety", 15);
        result.put("depression", 20);
        result.put("suggestion", EMOTION_SUGGESTIONS.get("平静"));
        return result;
    }

    static {
        EMOTION_MAP.put("happy", "开心");
        EMOTION_MAP.put("sad", "悲伤");
        EMOTION_MAP.put("angry", "愤怒");
        EMOTION_MAP.put("fear", "恐惧");
        EMOTION_MAP.put("surprise", "惊讶");
        EMOTION_MAP.put("neutral", "平静");
        EMOTION_MAP.put("disgust", "厌恶");
        EMOTION_MAP.put("calm", "平静");
        EMOTION_SUGGESTIONS.put("开心", "继续保持愉悦的心情！开心是最好的能量来源，可以把这份快乐分享给身边的人。");
        EMOTION_SUGGESTIONS.put("平静", "保持这个平和的状态，适合进行需要专注的工作或学习。");
        EMOTION_SUGGESTIONS.put("惊讶", "有什么事情让你意外吗？先冷静下来，了解更多情况后再做反应。");
        EMOTION_SUGGESTIONS.put("悲伤", "允许自己感受悲伤，这是正常的情绪反应。如果需要，可以找信任的人倾诉或寻求专业帮助。");
        EMOTION_SUGGESTIONS.put("愤怒", "先深呼吸，离开让你生气的地方。等冷静后，再思考如何处理问题。");
        EMOTION_SUGGESTIONS.put("恐惧", "面对恐惧时，可以尝试放松训练。如果恐惧感很强，建议寻求专业帮助。");
        EMOTION_SUGGESTIONS.put("厌恶", "可能有什么事情让你不舒服。尝试远离让你产生厌恶感的事物。");
    }
}
