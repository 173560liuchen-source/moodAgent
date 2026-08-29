package com.example.app.service;

import java.util.Map;

public interface EmotionService {
    Map<String, Object> analyzeEmotion(byte[] imageBytes);
}