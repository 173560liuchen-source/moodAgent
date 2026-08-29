package com.example.app.controller;

import com.example.app.entity.User;
import com.example.app.mapper.UserMapper;
import com.example.app.utils.JwtTokenUtil;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.LocalDateTime;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestTemplate;

@RestController
@RequestMapping({"/wx"})
public class WxLoginController {
    @Value("${wechat.app-id}")
    private String appid;
    @Value("${wechat.app-secret}")
    private String secret;
    @Autowired
    private UserMapper userMapper;
    @Autowired
    private JwtTokenUtil jwtTokenUtil;
    private final RestTemplate restTemplate = new RestTemplate();
    private final ObjectMapper objectMapper = new ObjectMapper();

    public WxLoginController() {
    }

    @PostMapping({"/login"})
    public Map<String, Object> login(@RequestBody Map<String, String> data) {
        String code = (String)data.get("code");
        String nickname = (String)data.get("nickname");
        String avatar = (String)data.getOrDefault("avatar", "");
        Integer gender = 0;
        if (data.containsKey("gender")) {
            try {
                gender = Integer.parseInt((String)data.get("gender"));
            } catch (NumberFormatException var16) {
                gender = 0;
            }
        }

        if (code == null || code.isBlank()) {
            return this.errorResult("缺少微信登录凭证");
        }
        String url = "https://api.weixin.qq.com/sns/jscode2session?appid="
                + URLEncoder.encode(this.appid, StandardCharsets.UTF_8)
                + "&secret=" + URLEncoder.encode(this.secret, StandardCharsets.UTF_8)
                + "&js_code=" + URLEncoder.encode(code, StandardCharsets.UTF_8)
                + "&grant_type=authorization_code";

        try {
            String response = (String)this.restTemplate.getForObject(url, String.class, new Object[0]);
            if (response == null) {
                return this.errorResult("微信接口返回为空");
            } else {
                Map<String, Object> wxRes = (Map)this.objectMapper.readValue(response, Map.class);
                String openid = (String)wxRes.get("openid");
                if (openid == null) {
                    String errmsg = (String)wxRes.get("errmsg");
                    return this.errorResult("微信登录失败: " + (errmsg != null ? errmsg : "未知错误"));
                } else {
                    User user = this.userMapper.selectByOpenid(openid);
                    if (user == null) {
                        user = new User();
                        user.setOpenid(openid);
                        user.setNickname(nickname);
                        user.setAvatar(avatar);
                        user.setGender(gender);
                        user.setCreateTime(LocalDateTime.now());
                        this.userMapper.insert(user);
                    } else {
                        user.setNickname(nickname);
                        user.setAvatar(avatar);
                        user.setGender(gender);
                        this.userMapper.update(user);
                    }

                    String token = this.jwtTokenUtil.generateToken(openid, user.getId());
                    LocalDateTime tokenExpireTime = this.jwtTokenUtil.getExpirationTime(token);
                    this.userMapper.updateToken(openid, token, tokenExpireTime);
                    Map<String, Object> result = new HashMap();
                    result.put("code", 200);
                    result.put("message", "登录成功");
                    Map<String, Object> dataMap = new HashMap();
                    dataMap.put("token", token);
                    dataMap.put("openid", openid);
                    dataMap.put("userId", user.getId());
                    dataMap.put("nickname", user.getNickname());
                    dataMap.put("avatar", user.getAvatar());
                    result.put("data", dataMap);
                    return result;
                }
            }
        } catch (Exception var15) {
            var15.printStackTrace();
            return this.errorResult("登录异常: " + var15.getMessage());
        }
    }

    @PostMapping({"/verify"})
    public Map<String, Object> verifyToken(@RequestBody Map<String, String> data) {
        String token = (String)data.get("token");
        if (token != null && !token.isEmpty()) {
            if (!this.jwtTokenUtil.validateToken(token)) {
                return this.errorResult("Token无效或已过期");
            } else {
                User user = this.userMapper.findByToken(token);
                if (user == null) {
                    return this.errorResult("用户不存在或Token已过期");
                } else {
                    Map<String, Object> result = new HashMap();
                    result.put("code", 200);
                    result.put("message", "验证成功");
                    Map<String, Object> dataMap = new HashMap();
                    dataMap.put("userId", user.getId());
                    dataMap.put("openid", user.getOpenid());
                    dataMap.put("nickname", user.getNickname());
                    dataMap.put("avatar", user.getAvatar());
                    result.put("data", dataMap);
                    return result;
                }
            }
        } else {
            return this.errorResult("Token不能为空");
        }
    }

    @PostMapping({"/logout"})
    public Map<String, Object> logout(@RequestBody Map<String, String> data) {
        String token = (String)data.get("token");
        if (token != null && !token.isEmpty()) {
            String openid = this.jwtTokenUtil.getOpenidFromToken(token);
            if (openid != null) {
                this.userMapper.clearToken(openid);
            }
        }

        Map<String, Object> result = new HashMap();
        result.put("code", 200);
        result.put("message", "退出成功");
        return result;
    }

    private Map<String, Object> errorResult(String message) {
        Map<String, Object> result = new HashMap();
        result.put("code", 500);
        result.put("message", message);
        return result;
    }
}
