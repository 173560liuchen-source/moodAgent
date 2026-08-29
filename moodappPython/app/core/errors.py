class AgentServiceError(RuntimeError):
    code = "AGENT_SERVICE_ERROR"
    retryable = False


class AgentDependencyError(AgentServiceError):
    code = "AGENT_DEPENDENCY_ERROR"
    retryable = True


class AgentContractError(AgentServiceError):
    code = "AGENT_CONTRACT_ERROR"
    retryable = False


class AgentValidationError(AgentContractError):
    code = "AGENT_VALIDATION_ERROR"
