CREATE TABLE IF NOT EXISTS intervention_follow_up (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    plan_id BIGINT NULL,
    request_id VARCHAR(80) NULL,
    adjusted_plan_request_id VARCHAR(80) NULL,
    feedback_text VARCHAR(1000) NOT NULL,
    adherence VARCHAR(32) NOT NULL,
    effectiveness VARCHAR(32) NOT NULL,
    decision VARCHAR(32) NOT NULL,
    emotion_change VARCHAR(64) NULL,
    risk_change VARCHAR(64) NULL,
    evidence TEXT NULL,
    adjustment_reason VARCHAR(1000) NULL,
    confidence DECIMAL(5,4) NULL,
    create_time DATETIME NOT NULL,
    INDEX idx_intervention_follow_up_user_time (user_id, create_time),
    INDEX idx_intervention_follow_up_plan (plan_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
