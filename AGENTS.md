# Trading Bot repository instructions

These instructions apply to the entire repository and are intentionally shared by Cursor, Kilo Code, and other coding agents.

## Architecture and source of truth

- `Languages/Python` owns the product runtime, strategy, risk, exchange execution, service API, validation, and canonical option catalogs.
- `apps/desktop-pyqt` and `apps/service-api` are product entrypoints into that Python implementation.
- `experiments/native-cpp` and `experiments/rust-shells` must preserve Python contracts; they do not independently redefine trading behavior.
- Do not hand-edit generated parity files. Change `Languages/Python/app/native_parity.py` or its source catalogs, then run `python Languages/Python/tools/generate_native_parity_contracts.py`.

## Trading and secret safety

- LLM output is advisory-only. Never connect model output directly to order placement, leverage changes, position closing, stop-loss changes, or risk overrides.
- Keep deterministic strategy, risk, take-profit, stop-loss, and exchange execution in the owned runtime.
- Never commit API keys, tokens, account data, private prompts, or unredacted trading context. Prefer environment-variable references and the existing credential-store paths.
- Preserve the public-network opt-in checks for custom/local endpoints and the output-policy checks for LLM responses.

## LLM compatibility

- Keep model fields editable. Static model IDs are suggestions and historical fallbacks, not an availability guarantee.
- Preserve live model discovery through `GET /api/v1/llm/models`, and merge discovered IDs with static, historical, and user-supplied IDs.
- Preserve provider-selectable API styles: OpenAI Chat Completions, OpenAI Responses, Anthropic Messages, and Gemini `generateContent`.
- Treat reasoning effort, speed/service tier, and verbosity as validated provider option tokens so future values can pass through safely.
- Advanced request JSON may add provider options, but it must not replace model, prompt/instructions/messages, tools, tool choice, functions, contents, or streaming controls.
- Kilo uses `https://api.kilo.ai/api/gateway` and `provider/model` IDs. Do not hardcode an editor model in repository rules.
- Cursor is a supported development environment through these repository instructions; it is not represented as a runtime inference provider unless Cursor publishes a supported gateway contract.

## Verification

- Run focused tests for every changed surface, then the repository verification gate appropriate to the change.
- For LLM changes, cover provider catalog/config validation, request serialization, context redaction/bounding, output policy, model discovery, generated parity, Rust, native C++, and Tauri UI behavior.
- Preserve unrelated user changes and do not weaken tests or safety checks to make a build pass.
