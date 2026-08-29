package com.example.app.controller;

import com.example.app.dto.ApiResponse;
import com.example.app.entity.User;
import com.example.app.mapper.UserMapper;
import com.example.app.utils.JwtTokenUtil;
import com.example.app.utils.PasswordHasher;
import jakarta.annotation.Resource;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Pattern;

@RestController
@RequestMapping("/auth")
public class AuthController {

    private static final Pattern ACCOUNT_PATTERN = Pattern.compile("[A-Za-z0-9_@.-]{3,64}");

    @Resource
    private UserMapper userMapper;
    @Resource
    private JwtTokenUtil jwtTokenUtil;
    @Resource
    private PasswordHasher passwordHasher;

    @PostMapping("/register")
    public ApiResponse<Map<String, Object>> register(@RequestBody Map<String, String> body) {
        String account = normalize(body.get("account"));
        String nickname = normalize(body.get("nickname"));
        String password = body.get("password");
        String validation = validate(account, password);
        if (validation != null) {
            return ApiResponse.error(400, validation);
        }
        if (nickname.isBlank()) {
            nickname = account;
        }
        if (nickname.length() > 30) {
            return ApiResponse.error(400, "昵称不能超过30个字符");
        }
        if (userMapper.selectByOpenid(account) != null) {
            return ApiResponse.error(409, "账号已存在");
        }

        User user = new User();
        user.setOpenid(account);
        user.setPasswordHash(passwordHasher.hash(password));
        user.setNickname(nickname);
        user.setAvatar("");
        user.setGender(0);
        user.setMood("neutral");
        user.setCreateTime(LocalDateTime.now());
        try {
            userMapper.insertAccountUser(user);
        } catch (DuplicateKeyException duplicate) {
            return ApiResponse.error(409, "账号已存在");
        }
        return ApiResponse.success("注册成功", issueToken(user));
    }

    @PostMapping("/login")
    public ApiResponse<Map<String, Object>> login(@RequestBody Map<String, String> body) {
        String account = normalize(body.get("account"));
        String password = body.get("password");
        if (account.isBlank() || password == null || password.isBlank()) {
            return ApiResponse.error(400, "请输入账号和密码");
        }
        User user = userMapper.selectByOpenid(account);
        if (user == null || !passwordHasher.matches(password, user.getPasswordHash())) {
            return ApiResponse.error(401, "账号或密码错误");
        }
        return ApiResponse.success("登录成功", issueToken(user));
    }

    @GetMapping("/me")
    public ApiResponse<Map<String, Object>> me(HttpServletRequest request) {
        User user = (User) request.getAttribute("currentUser");
        return ApiResponse.success(publicUser(user));
    }

    @PostMapping("/logout")
    public ApiResponse<Void> logout(HttpServletRequest request) {
        User user = (User) request.getAttribute("currentUser");
        if (user != null) {
            userMapper.clearToken(user.getOpenid());
        }
        return ApiResponse.success("已退出登录", null);
    }

    private Map<String, Object> issueToken(User user) {
        String token = jwtTokenUtil.generateToken(user.getOpenid(), user.getId());
        userMapper.updateToken(user.getOpenid(), token, jwtTokenUtil.getExpirationTime(token));
        Map<String, Object> result = new LinkedHashMap<>(publicUser(user));
        result.put("token", token);
        return result;
    }

    private Map<String, Object> publicUser(User user) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("userId", user.getId());
        result.put("account", user.getOpenid());
        result.put("nickname", user.getNickname());
        result.put("avatar", user.getAvatar() == null ? "" : user.getAvatar());
        return result;
    }

    private String validate(String account, String password) {
        if (!ACCOUNT_PATTERN.matcher(account).matches()) {
            return "账号需为3-64位字母、数字或 _ @ . -";
        }
        if (password == null || password.length() < 8 || password.length() > 72) {
            return "密码长度需为8-72位";
        }
        return null;
    }

    private String normalize(String value) {
        return value == null ? "" : value.trim();
    }
}
