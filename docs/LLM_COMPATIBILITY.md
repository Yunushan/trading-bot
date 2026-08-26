# LLM, Cursor, and Kilo compatibility

The project is capability-forward-compatible rather than claiming that every model ID will remain available forever. Model availability, accepted parameters, context limits, and retired IDs are ultimately controlled by the selected provider and account.

## Runtime providers and protocols

The LLM configuration supports OpenAI, Kilo AI Gateway, Anthropic, Gemini, DeepSeek, Mistral, xAI, Qwen/DashScope, Moonshot/Kimi, OpenAI-compatible local servers, Ollama, vLLM/SGLang, llama.cpp, LM Studio, Hugging Face TGI, and a broad open-source profile.

Requests can use:

- OpenAI Chat Completions
- OpenAI Responses
- Anthropic Messages
- Gemini `generateContent`

The API style is selectable independently when an endpoint supports more than one protocol. The model field remains editable, so a newly released or private model does not require a catalog release.

## Models, old IDs, and discovery

`GET /api/v1/llm/models` queries the configured provider's model-list endpoint and merges live results with:

- current catalog suggestions;
- historical model IDs;
- the currently selected custom ID;
- `BOT_LLM_EXTRA_MODELS_<PROVIDER>` values; and
- a JSON catalog selected by `BOT_LLM_MODEL_CATALOG_PATH`.

A historical ID being selectable does not mean an upstream provider still serves it. A live discovery result means the provider listed the ID, while request acceptance is still authoritative.

Kilo is a first-class runtime provider with base URL `https://api.kilo.ai/api/gateway`, live `/models` discovery, stable `kilo-auto/*` suggestions, arbitrary `provider/model` IDs, and Chat Completions or Responses request styles.

## Capability controls

The shared config and desktop surfaces expose:

- `llm_api_style`
- `llm_reasoning_effort`
- `llm_speed`
- `llm_context_window`
- `llm_max_output_tokens`
- `llm_verbosity`
- `llm_temperature`
- `llm_top_p`
- `llm_timeout_seconds`
- `llm_request_options`

Reasoning, speed, and verbosity accept safe provider option tokens in addition to known suggestions. Context is bounded before transmission when a window is configured. Output and sampling fields are translated to each protocol's field names. Advanced request JSON is deep-merged, but protected model, prompt, message, tool, content, and stream fields are ignored.

## Cursor and Kilo Code

- Cursor reads the root `AGENTS.md` and `.cursor/rules/trading-bot.mdc`. These rules support repository development without pinning the user's Cursor model.
- Kilo reads `kilo.jsonc`, `AGENTS.md`, and `.kilo/rules/trading-bot.md`. Its model and mode remain user-controlled.
- Cursor is an editor/development compatibility target here, not a fabricated runtime LLM gateway. Kilo is both a development environment and a configured application runtime provider.

## Safety boundary

All LLM paths are advisory-only. Requests prepend the execution boundary, cloud/public context is minimized and redacted, configured context can be bounded, and outputs are blocked if they attempt direct order actions, claim execution, or override deterministic risk controls.
