ALTER TABLE intervention_plan
    ADD COLUMN parent_plan_id BIGINT NULL AFTER user_id,
    ADD COLUMN revision_no INT NOT NULL DEFAULT 0 AFTER parent_plan_id,
    ADD COLUMN decision_source VARCHAR(20) NOT NULL DEFAULT 'initial' AFTER revision_no,
    ADD INDEX idx_intervention_plan_parent (parent_plan_id),
    ADD INDEX idx_intervention_plan_user_revision (user_id, revision_no);
