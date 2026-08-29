package com.example.app.service.Impl;

import com.example.app.entity.RiskReport;
import com.example.app.mapper.RiskReportMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class RiskReportService {
    @Autowired
    private RiskReportMapper riskReportMapper;

    public RiskReport getLatest(Long userId){

        return riskReportMapper.findLatest(userId);

    }
}
