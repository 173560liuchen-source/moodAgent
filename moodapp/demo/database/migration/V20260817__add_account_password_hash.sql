ALTER TABLE user
    ADD COLUMN password_hash VARCHAR(255) NULL AFTER openid;
