package com.example.app.controller;

import com.example.app.dto.ApiResponse;
import com.example.app.service.TrendService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

//趋势分析控制器
@RestController
@RequestMapping("/trend")
public class TrendController {

    @Autowired
    private TrendService trendService;

    @PostMapping("/generate")
    public ApiResponse<String> generateTrend(@RequestParam String openId) {

        trendService.generateTrend(openId);

        return ApiResponse.success("生成成功");

    }

    //获取最新结果
    @GetMapping("/latest")
    public ApiResponse<Object> latest(@RequestParam String openId){

        return ApiResponse.success(trendService.findLatest(openId));
    }
}
