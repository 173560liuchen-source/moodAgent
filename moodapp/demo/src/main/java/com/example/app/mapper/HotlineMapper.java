package com.example.app.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.example.app.entity.Hotline;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface HotlineMapper extends BaseMapper<Hotline> {
    @Select({"SELECT * FROM hotline"})
    List<Hotline> select(Object o);
}
