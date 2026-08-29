package com.example.app.controller;

import com.alibaba.fastjson.JSON;
import com.example.app.dto.ApiResponse;
import com.example.app.dto.RiskReportVO;
import com.example.app.entity.RiskReport;
import com.example.app.entity.User;
import com.example.app.mapper.UserMapper;
import com.example.app.service.Impl.RiskAnalysisService;
import com.example.app.service.Impl.RiskReportService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Collections;
import java.util.List;

@Slf4j
@RestController
@RequestMapping("/risk")
public class RiskReportController {

    @Autowired
    private RiskReportService riskReportService;

    @Autowired
    private RiskAnalysisService riskAnalysisService;

    @Autowired
    private UserMapper userMapper;

    @PostMapping("/generate")
    public ApiResponse<RiskReportVO> generate(@RequestParam String openid) {
        User user = findUserByOpenid(openid);
        RiskReport report = riskAnalysisService.generateAndSaveRiskReport(user.getId());
        return ApiResponse.success(toVO(report));
    }

    @GetMapping("/latest")
    public ApiResponse<RiskReportVO> latest(@RequestParam String openid) {
        User user = findUserByOpenid(openid);
        RiskReport report = riskReportService.getLatest(user.getId());

        if (report == null) {
            return ApiResponse.error("暂无风险报告数据");
        }

        return ApiResponse.success(toVO(report));
    }

    private User findUserByOpenid(String openid) {
        if (openid == null || openid.isBlank()) {
            throw new IllegalArgumentException("openid不能为空");
        }

        User user = userMapper.selectByOpenid(openid);
        if (user == null) {
            throw new IllegalArgumentException("用户不存在");
        }
        return user;
    }

    private RiskReportVO toVO(RiskReport report) {
        RiskReportVO vo = new RiskReportVO();
        vo.setRiskLevel(report.getRiskLevel());
        vo.setNeedCenter(report.getNeedCenter());
        vo.setConclusion(report.getConclusion());
        vo.setUserFriendlyReport(report.getUserFriendlyReport());
        vo.setRiskReasons(parseStringArray(report.getRiskReasons()));
        vo.setDangerSignals(parseStringArray(report.getDangerSignals()));
        vo.setSuggestions(parseStringArray(report.getSuggestions()));
        return vo;
    }

    private List<String> parseStringArray(String raw) {
        if (raw == null || raw.isBlank()) {
            return Collections.emptyList();
        }
        try {
            return JSON.parseArray(raw, String.class);
        } catch (RuntimeException ex) {
            log.warn("Risk report field is not a JSON array, fallback to raw text.");
            return List.of(raw);
        }
    }
}
