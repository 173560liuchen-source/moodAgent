package com.example.app.mapper;

import com.example.app.entity.RagRetrievalLog;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface RagRetrievalLogMapper {

    @Insert("INSERT INTO rag_retrieval_log " +
            "(user_id, request_id, query_text, rewritten_query, selected_categories, citations, has_evidence, no_evidence_reason, retrieval_strategy, confidence, create_time) " +
            "VALUES " +
            "(#{userId}, #{requestId}, #{queryText}, #{rewrittenQuery}, #{selectedCategories}, #{citations}, #{hasEvidence}, #{noEvidenceReason}, #{retrievalStrategy}, #{confidence}, #{createTime})")
    int insert(RagRetrievalLog log);

    @Select("SELECT * FROM rag_retrieval_log WHERE request_id = #{requestId} LIMIT 1")
    RagRetrievalLog findByRequestId(@Param("requestId") String requestId);

    @Select("SELECT * FROM rag_retrieval_log WHERE user_id = #{userId} ORDER BY create_time DESC LIMIT #{limit}")
    List<RagRetrievalLog> findRecentByUserId(@Param("userId") Long userId, @Param("limit") int limit);
}
