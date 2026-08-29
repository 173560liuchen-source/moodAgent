package com.example.app.token;

import com.example.app.entity.User;
import com.example.app.mapper.UserMapper;
import com.example.app.utils.JwtTokenUtil;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.util.HashMap;
import java.util.Map;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
public class AuthInterceptor implements HandlerInterceptor {
    @Autowired
    private JwtTokenUtil jwtTokenUtil;
    @Autowired
    private UserMapper userMapper;
    private static final String[] WHITE_LIST = new String[]{
            "/wx/login", "/wx/verify", "/wx/logout",
            "/auth/login", "/auth/register", "/help/hotline"
    };

    public AuthInterceptor() {
    }

    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) throws Exception {
        response.setCharacterEncoding("UTF-8");
        response.setContentType("application/json;charset=UTF-8");
        String path = request.getRequestURI();
        String method = request.getMethod();
        if ("OPTIONS".equalsIgnoreCase(method)) {
            return true;
        } else {
            String[] var6 = WHITE_LIST;
            int var7 = var6.length;

            for(int var8 = 0; var8 < var7; ++var8) {
                String whitePath = var6[var8];
                if (path.equals(whitePath)) {
                    return true;
                }
            }

            String token = request.getHeader("Authorization");
            if (token != null && token.startsWith("Bearer ")) {
                token = token.substring(7);
            }

            if (token != null && !token.isEmpty()) {
                if (!this.jwtTokenUtil.validateToken(token)) {
                    this.sendUnauthorized(response, "Token无效或已过期，请重新登录");
                    return false;
                } else {
                    User user = this.userMapper.findByToken(token);
                    if (user == null) {
                        this.sendUnauthorized(response, "用户不存在或登录已过期，请重新登录");
                        return false;
                    } else {
                        String requestedUserId = request.getParameter("userId");
                        if (requestedUserId != null && !requestedUserId.isBlank()) {
                            try {
                                if (!user.getId().equals(Long.valueOf(requestedUserId))) {
                                    this.sendForbidden(response, "无权访问其他用户的数据");
                                    return false;
                                }
                            } catch (NumberFormatException invalidUserId) {
                                this.sendForbidden(response, "userId格式错误");
                                return false;
                            }
                        }
                        request.setAttribute("currentUser", user);
                        request.setAttribute("userId", user.getId());
                        request.setAttribute("openid", user.getOpenid());
                        return true;
                    }
                }
            } else {
                this.sendUnauthorized(response, "请先登录");
                return false;
            }
        }
    }

    private void sendUnauthorized(HttpServletResponse response, String message) throws Exception {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        Map<String, Object> result = new HashMap();
        result.put("code", 401);
        result.put("message", message);
        ObjectMapper mapper = new ObjectMapper();
        response.getWriter().write(mapper.writeValueAsString(result));
    }

    private void sendForbidden(HttpServletResponse response, String message) throws Exception {
        response.setStatus(HttpServletResponse.SC_FORBIDDEN);
        Map<String, Object> result = new HashMap();
        result.put("code", 403);
        result.put("message", message);
        ObjectMapper mapper = new ObjectMapper();
        response.getWriter().write(mapper.writeValueAsString(result));
    }
}
