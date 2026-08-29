package com.example.app.config;

import com.example.app.token.AuthInterceptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebMvcConfig implements WebMvcConfigurer {
    @Autowired
    private AuthInterceptor authInterceptor;
    public WebMvcConfig() {
    }

    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(this.authInterceptor)
                .addPathPatterns(new String[]{"/**"})
                .excludePathPatterns(new String[]{
                        "/wx/login",
                        "/wx/verify",
                        "/wx/logout",
                        "/auth/login",
                        "/auth/register",
                        "/help/hotline",
                        "/error"
                });
    }
}
