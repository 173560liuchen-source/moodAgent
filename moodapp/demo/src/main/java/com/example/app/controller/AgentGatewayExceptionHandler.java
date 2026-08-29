package com.example.app.controller;

import com.alibaba.fastjson.JSONObject;
import com.example.app.dto.ApiResponse;
import com.example.app.service.Impl.PythonOrchestratorService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice(assignableTypes = {
        AgentGatewayController.class,
        PythonAgentController.class
})
public class AgentGatewayExceptionHandler {

    @ExceptionHandler(PythonOrchestratorService.PythonOrchestratorException.class)
    public ResponseEntity<ApiResponse<JSONObject>> handlePythonAgentError(
            PythonOrchestratorService.PythonOrchestratorException exception
    ) {
        JSONObject detail = new JSONObject();
        detail.put("upstream", "moodapp-python-agent");
        detail.put("retryable", true);
        detail.put("reason", exception.getMessage());
        ApiResponse<JSONObject> response = ApiResponse.error(
                HttpStatus.BAD_GATEWAY.value(),
                "Python智能体服务暂时不可用"
        );
        response.setData(detail);
        return ResponseEntity
                .status(HttpStatus.BAD_GATEWAY)
                .body(response);
    }
}
