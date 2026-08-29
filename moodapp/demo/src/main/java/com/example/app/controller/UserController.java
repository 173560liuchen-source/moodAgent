package com.example.app.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.example.app.entity.User;
import com.example.app.mapper.UserMapper;
import jakarta.annotation.Resource;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping({"/user"})
public class UserController {
    @Resource
    private UserMapper userMapper;

    public UserController() {
    }

    @PostMapping({"/login"})
    public User login(@RequestBody User user) {
        LambdaQueryWrapper<User> wrapper = new LambdaQueryWrapper();
        wrapper.eq(User::getOpenid, user.getOpenid());
        User existUser = (User)this.userMapper.selectOne(wrapper);
        if (existUser == null) {
            this.userMapper.insert(user);
            return user;
        } else {
            return existUser;
        }
    }
}
