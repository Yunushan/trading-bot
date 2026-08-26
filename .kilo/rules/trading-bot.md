# Kilo guidance for Trading Bot

Use `AGENTS.md` as the repository-wide contract.

- Keep Kilo model selection user-controlled; do not pin a model in project configuration.
- For the application's Kilo runtime provider, use the OpenAI-compatible gateway base URL `https://api.kilo.ai/api/gateway` and retain `provider/model` identifiers exactly.
- Use live model discovery when availability matters. Keep static and historical IDs selectable because an account or custom gateway may still expose them.
- Preserve arbitrary validated effort, speed/service-tier, verbosity, context, output, sampling, timeout, and protected advanced-request options.
- LLM responses remain advisory-only and cannot execute or claim execution of trades.
- Update Python source contracts first and regenerate native parity outputs before editing native consumers.
