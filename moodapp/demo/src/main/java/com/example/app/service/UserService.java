package com.example.app.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.example.app.entity.User;

public interface UserService {
    User findByOpenid(String openid);

    User selectOne(LambdaQueryWrapper<User> wrapper);

    User createUser(User user);

    void updateUser(User user);

    void updateMood(Long userId, String mood);

    void updateAssessmentScore(String openid, Integer score);

    User findById(Long id);
}