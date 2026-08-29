package com.example.app.entity;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Data
@AllArgsConstructor
@NoArgsConstructor
public class ChatRecord {
    private Long id;
    private Long userId;
    private String role;
    private String content;
    private String emotion;

    /** 该消息所属编排请求；用于将一轮对话与审计链精确关联。 */
    private String requestId;

    /** 该消息所属会话；与编排上下文的 session_id 保持一致。 */
    private String sessionId;

    private LocalDateTime createTime;
}
