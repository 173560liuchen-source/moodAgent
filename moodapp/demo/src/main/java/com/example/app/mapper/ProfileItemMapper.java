package com.example.app.mapper;

import com.example.app.entity.ProfileItem;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;

@Mapper
public interface ProfileItemMapper {

    @Insert("INSERT INTO profile_item " +
            "(user_id, category, value, source, evidence, confidence, editable, deletable, sensitivity, status, create_time, update_time) " +
            "VALUES " +
            "(#{userId}, #{category}, #{value}, #{source}, #{evidence}, #{confidence}, #{editable}, #{deletable}, #{sensitivity}, #{status}, #{createTime}, #{updateTime})")
    int insert(ProfileItem item);

    @Select("SELECT * FROM profile_item WHERE user_id = #{userId} AND status = 'active' ORDER BY update_time DESC LIMIT 50")
    List<ProfileItem> findEnabledByUserId(Long userId);

    @Update("UPDATE profile_item SET value = #{value}, evidence = #{evidence}, update_time = NOW() " +
            "WHERE id = #{id} AND user_id = #{userId} AND editable = 1 AND status = 'active'")
    int updateEditableItem(@Param("id") Long id,
                           @Param("userId") Long userId,
                           @Param("value") String value,
                           @Param("evidence") String evidence);

    @Update("UPDATE profile_item SET status = 'deleted', update_time = NOW() " +
            "WHERE id = #{id} AND user_id = #{userId} AND deletable = 1 AND status = 'active'")
    int softDeleteItem(@Param("id") Long id, @Param("userId") Long userId);
}
