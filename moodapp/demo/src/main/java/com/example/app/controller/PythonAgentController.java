package com.example.app.controller;

import com.alibaba.fastjson.JSONObject;
import com.example.app.dto.ApiResponse;
import com.example.app.service.Impl.PythonOrchestratorService;
import jakarta.annotation.Resource;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/agent")
public class PythonAgentController {

    @Resource
    private PythonOrchestratorService pythonOrchestratorService;

    @GetMapping("/health")
    public ApiResponse<JSONObject> health() {
        return ApiResponse.success(pythonOrchestratorService.health());
    }

    @GetMapping("/ready")
    public ApiResponse<JSONObject> ready() {
        return ApiResponse.success(pythonOrchestratorService.ready());
    }

    @GetMapping("/model/status")
    public ApiResponse<JSONObject> modelStatus() {
        return ApiResponse.success(pythonOrchestratorService.modelStatus());
    }
}
