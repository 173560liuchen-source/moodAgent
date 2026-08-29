CREATE TABLE IF NOT EXISTS intervention_action_feedback (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    plan_id BIGINT NOT NULL,
    action_id VARCHAR(40) NOT NULL,
    execution_status VARCHAR(20) NOT NULL,
    outcome_status VARCHAR(20) NOT NULL,
    difficulty TINYINT NULL,
    feedback_note VARCHAR(500) NULL,
    source VARCHAR(20) NOT NULL DEFAULT 'page',
    create_time DATETIME NOT NULL,
    INDEX idx_intervention_action_feedback_user_time (user_id, create_time),
    INDEX idx_intervention_action_feedback_plan_action (plan_id, action_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
