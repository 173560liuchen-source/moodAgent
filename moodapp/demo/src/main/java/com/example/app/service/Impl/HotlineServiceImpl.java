package com.example.app.service.Impl;

import com.example.app.entity.Hotline;
import com.example.app.mapper.HotlineMapper;
import com.example.app.service.HotlineService;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class HotlineServiceImpl implements HotlineService {
    @Autowired
    private HotlineMapper hotlineMapper;

    public HotlineServiceImpl() {
    }

    public List<Hotline> selectList(Object o) {
        return this.hotlineMapper.select((Object)null);
    }
}
