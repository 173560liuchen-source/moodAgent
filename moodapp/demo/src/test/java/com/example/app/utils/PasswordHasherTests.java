package com.example.app.utils;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class PasswordHasherTests {

    private final PasswordHasher hasher = new PasswordHasher();

    @Test
    void hashUsesRandomSaltAndOnlyMatchesOriginalPassword() {
        String first = hasher.hash("safe-password-123");
        String second = hasher.hash("safe-password-123");

        assertThat(first).startsWith("pbkdf2_sha256$");
        assertThat(first).isNotEqualTo(second);
        assertThat(hasher.matches("safe-password-123", first)).isTrue();
        assertThat(hasher.matches("wrong-password", first)).isFalse();
    }

    @Test
    void malformedOrUnreasonablyExpensiveHashesAreRejected() {
        assertThat(hasher.matches("x", "plain-text")).isFalse();
        assertThat(hasher.matches("x", "pbkdf2_sha256$999999999$AA==$AA==")).isFalse();
    }
}
