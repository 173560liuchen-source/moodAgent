package com.example.app.utils;

import jakarta.servlet.http.HttpServletRequest;

public final class AuthenticatedUser {

    private AuthenticatedUser() {
    }

    public static Long requireId(HttpServletRequest request) {
        Object value = request.getAttribute("userId");
        if (value instanceof Long userId) {
            return userId;
        }
        throw new IllegalStateException("缺少已认证用户身份");
    }
}
