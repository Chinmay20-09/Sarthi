from dataclasses import dataclass


@dataclass
class HermesConfig:
    # One authoritative default: local-first (Ollama, no cloud). Remote
    # providers (openrouter / openai_compatible / openai) are opt-in via
    # HERMES_PROVIDER and get an automatic local fallback when selected.
    provider: str = "local"
    model: str = "openai/gpt-5"
    temperature: float = 0.2
    timeout: float = 60.0
    # Sandbox root. A relative value (the default) is resolved against the
    # backend root by hermes.sandbox.resolve_sandbox_root, so the same task
    # lands in the same store regardless of the launch directory. Absolute
    # values (HERMES_SANDBOX_PATH, tests) are used as given.
    sandbox_path: str = "sandbox"
    # OpenRouter settings (only used when provider=openrouter)
    openrouter_api_key: str = ""
    openrouter_url: str = "https://openrouter.ai/api/v1/chat/completions"
    openrouter_http_referer: str = ""
    openrouter_x_title: str = "Sarthi"
    # Generic OpenAI-compatible endpoint (provider=openai_compatible or openai).
    # Points at OpenAI by default; point it at any /v1-compatible endpoint
    # (LM Studio, vLLM, Together, ...) to use that service instead.
    openai_compatible_url: str = "https://api.openai.com/v1"
    openai_compatible_api_key: str = ""
    # Local Hermes settings (Ollama)
    local_hermes_url: str = "http://localhost:11434"
    local_hermes_api_key: str = ""
    # Local model name as installed in Ollama (distinct from the OpenRouter model)
    local_model: str = "hermes3:8b"
    # CPU-only inference is slow — default 180s (3x the base timeout)
    local_timeout: float = 180.0
    # legacy (falls back for providers without their own key field)
    api_key: str = ""
    # ------------------------------------------------------------------
    # Agent loop bounds (Phase 3f) — how long/many steps one complex task
    # may take. The loop is bounded by iterations AND wall-clock time.
    # Three automatic iterations is the architectural retry bound: a complex
    # task may take at most three model turns that request a tool.
    # ------------------------------------------------------------------
    agent_max_iterations: int = 3
    agent_timeout: float = 300.0
    # ------------------------------------------------------------------
    # Router knobs (Phase 3f) — the complexity gate in front of Hermes.
    # HERMES_ROUTER_MODE: "auto" (heuristics), "always" (everything to
    # Hermes; deterministic pipeline still runs first inside the agent),
    # or "off" (never route to Hermes from the /command pipeline).
    # ------------------------------------------------------------------
    router_mode: str = "auto"
    router_min_score: int = 1
    # ------------------------------------------------------------------
    # Retrieval knobs (Phase 3f) — bounding what the retriever feeds the
    # model. Character budgets keep prompts small enough for an 8B model.
    # ------------------------------------------------------------------
    retrieval_max_total_chars: int = 6000
    retrieval_enabled: bool = True
