package com.example.app.token;

import com.example.app.entity.User;
import com.example.app.mapper.UserMapper;
import com.example.app.utils.JwtTokenUtil;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.test.util.ReflectionTestUtils;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class AuthInterceptorTests {

    private AuthInterceptor interceptor;
    private JwtTokenUtil tokens;
    private UserMapper users;

    @BeforeEach
    void setUp() {
        interceptor = new AuthInterceptor();
        tokens = mock(JwtTokenUtil.class);
        users = mock(UserMapper.class);
        ReflectionTestUtils.setField(interceptor, "jwtTokenUtil", tokens);
        ReflectionTestUtils.setField(interceptor, "userMapper", users);
    }

    @Test
    void protectedEndpointRequiresAuthentication() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/chat/all");
        MockHttpServletResponse response = new MockHttpServletResponse();

        assertThat(interceptor.preHandle(request, response, new Object())).isFalse();
        assertThat(response.getStatus()).isEqualTo(401);
        assertThat(response.getContentAsString()).contains("请先登录");
    }

    @Test
    void authenticatedIdentityIsAttachedAndDifferentQueryUserIsRejected() throws Exception {
        User user = new User();
        user.setId(7L);
        user.setOpenid("account-7");
        when(tokens.validateToken("valid-token")).thenReturn(true);
        when(users.findByToken("valid-token")).thenReturn(user);

        MockHttpServletRequest accepted = requestFor("7");
        assertThat(interceptor.preHandle(accepted, new MockHttpServletResponse(), new Object())).isTrue();
        assertThat(accepted.getAttribute("userId")).isEqualTo(7L);

        MockHttpServletRequest rejected = requestFor("8");
        MockHttpServletResponse response = new MockHttpServletResponse();
        assertThat(interceptor.preHandle(rejected, response, new Object())).isFalse();
        assertThat(response.getStatus()).isEqualTo(403);
    }

    private MockHttpServletRequest requestFor(String userId) {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/chat/all");
        request.addHeader("Authorization", "Bearer valid-token");
        request.addParameter("userId", userId);
        return request;
    }
}
