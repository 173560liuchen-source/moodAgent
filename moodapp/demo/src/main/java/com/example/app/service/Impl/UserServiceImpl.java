package com.example.app.service.Impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.example.app.entity.User;
import com.example.app.mapper.UserMapper;
import com.example.app.service.UserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class UserServiceImpl implements UserService {
    @Autowired
    private UserMapper userMapper;

    public UserServiceImpl() {
    }

    public User findByOpenid(String openid) {
        return this.userMapper.selectByOpenid(openid);
    }

    public User selectOne(LambdaQueryWrapper<User> wrapper) {
        return (User)this.userMapper.selectOne(wrapper);
    }

    public User createUser(User user) {
        this.userMapper.insert(user);
        return user;
    }

    public void updateUser(User user) {
        this.userMapper.update(user);
    }

    public void updateMood(Long userId, String mood) {
        this.userMapper.updateMood(userId, mood);
    }

    public void updateAssessmentScore(String openid, Integer score) {
        this.userMapper.updateAssessmentScore(openid, score);
    }

    public User findById(Long id) {
        return this.userMapper.findById(id);
    }
}