package com.example.app.utils;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.SignatureAlgorithm;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.Date;
import javax.crypto.SecretKey;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class JwtTokenUtil {
    private static final long EXPIRE_TIME = 604800000L;
    private static final String ISSUER = "mental-health-app";

    @Value("${security.jwt.secret}")
    private String secret;

    public JwtTokenUtil() {
    }

    public String generateToken(String openid, Long userId) {
        Date now = new Date();
        Date expiration = new Date(now.getTime() + 604800000L);
        return Jwts.builder().setSubject(openid).claim("userId", userId).setIssuer("mental-health-app").setIssuedAt(now).setExpiration(expiration).signWith(this.getSigningKey(), SignatureAlgorithm.HS256).compact();
    }

    public boolean validateToken(String token) {
        try {
            Jwts.parserBuilder().setSigningKey(this.getSigningKey()).build().parseClaimsJws(token);
            return true;
        } catch (IllegalArgumentException | JwtException var3) {
            return false;
        }
    }

    public String getOpenidFromToken(String token) {
        Claims claims = this.getClaims(token);
        return claims.getSubject();
    }

    public Long getUserIdFromToken(String token) {
        Claims claims = this.getClaims(token);
        return (Long)claims.get("userId", Long.class);
    }

    public LocalDateTime getExpirationTime(String token) {
        Claims claims = this.getClaims(token);
        Date expiration = claims.getExpiration();
        return expiration.toInstant().atZone(ZoneId.systemDefault()).toLocalDateTime();
    }

    public boolean isTokenExpiringSoon(String token) {
        LocalDateTime expiration = this.getExpirationTime(token);
        return expiration.isBefore(LocalDateTime.now().plusDays(1L));
    }

    private Claims getClaims(String token) {
        return (Claims)Jwts.parserBuilder().setSigningKey(this.getSigningKey()).build().parseClaimsJws(token).getBody();
    }

    private SecretKey getSigningKey() {
        byte[] keyBytes = this.secret.getBytes(StandardCharsets.UTF_8);
        return Keys.hmacShaKeyFor(keyBytes);
    }
}
