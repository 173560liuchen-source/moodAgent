-- 让聊天管理页按 request_id 精确回放本轮智能体链，避免按时间猜测。
ALTER TABLE chat_record
    ADD COLUMN request_id VARCHAR(120) NULL AFTER emotion;

ALTER TABLE chat_record
    ADD COLUMN session_id VARCHAR(120) NULL AFTER request_id;

CREATE INDEX idx_chat_record_user_request ON chat_record (user_id, request_id);
CREATE INDEX idx_chat_record_user_session ON chat_record (user_id, session_id);
