package com.example.app.dto.python;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.ArrayList;
import java.util.List;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class PythonOrchestratorRequest {

    private String message;

    private List<PythonChatMessage> history = new ArrayList<>();

    private PythonAgentContext context;
}
