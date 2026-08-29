package com.example.app.service;

public interface TrendService {
    void generateTrend(String openId);

    Object findLatest(String openId);
}
