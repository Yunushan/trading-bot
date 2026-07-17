from __future__ import annotations

import copy
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LLMProviderSpec:
    key: str
    label: str
    mode: str
    protocol: str
    default_base_url: str
    default_model: str
    api_key_env: str
    model_suggestions: tuple[str, ...] = ()
    reasoning_efforts: tuple[str, ...] = ("default",)
    default_reasoning_effort: str = "default"
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["model_suggestions"] = list(self.model_suggestions)
        payload["reasoning_efforts"] = list(self.reasoning_efforts)
        payload["notes"] = list(self.notes)
        return payload


OPENAI_COMPATIBLE_PROTOCOL = "openai-chat-completions"
ANTHROPIC_MESSAGES_PROTOCOL = "anthropic-messages"
GEMINI_GENERATE_CONTENT_PROTOCOL = "gemini-generate-content"
LLM_PROVIDER_CATALOG_REVISION = "2026-07-16"
LLM_MODEL_CATALOG_PATH_ENV = "BOT_LLM_MODEL_CATALOG_PATH"

_OPEN_SOURCE_REASONING_EFFORTS = (
    "default",
    "none",
    "disabled",
    "auto",
    "low",
    "medium",
    "high",
    "xhigh",
)

_OPENAI_REASONING_EFFORTS = (
    "default",
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)

_OLLAMA_OPEN_SOURCE_MODELS = (
    "qwen3:0.6b",
    "qwen3:1.7b",
    "qwen3:4b",
    "qwen3:8b",
    "qwen3:14b",
    "qwen3:30b-a3b",
    "qwen3:32b",
    "qwen3",
    "qwen3-vl:8b",
    "qwen3-vl:32b",
    "qwen3.5",
    "qwen2.5:0.5b",
    "qwen2.5:1.5b",
    "qwen2.5:3b",
    "qwen2.5:7b",
    "qwen2.5:14b",
    "qwen2.5:32b",
    "qwen2.5:72b",
    "qwen2.5-coder:1.5b",
    "qwen2.5-coder:7b",
    "qwen2.5-coder:14b",
    "qwen2.5-coder:32b",
    "qwq:32b",
    "gpt-oss:20b",
    "gpt-oss:120b",
    "gpt-oss:latest",
    "llama4:maverick",
    "llama4:scout",
    "deepseek-v3",
    "deepseek-v3.1",
    "deepseek-v3.2",
    "deepseek-r1:1.5b",
    "deepseek-r1:7b",
    "deepseek-r1:8b",
    "deepseek-r1:14b",
    "deepseek-r1:32b",
    "deepseek-r1:70b",
    "deepseek-coder-v2",
    "llama3.3",
    "llama3.1:8b",
    "llama3.1:70b",
    "llama3.2:1b",
    "llama3.2:3b",
    "llama3.2-vision:11b",
    "llama3.2-vision:90b",
    "mistral",
    "mistral-nemo",
    "mistral-small3.2",
    "mixtral:8x7b",
    "mixtral:8x22b",
    "codestral",
    "devstral",
    "gemma3:1b",
    "gemma3:4b",
    "gemma3:12b",
    "gemma3:27b",
    "gemma4:27b",
    "gemma2:2b",
    "gemma2:9b",
    "gemma2:27b",
    "phi4",
    "phi4-mini",
    "phi3.5",
    "phi3:mini",
    "falcon3:1b",
    "falcon3:3b",
    "falcon3:7b",
    "falcon3:10b",
    "yi:6b",
    "yi:9b",
    "yi:34b",
    "glm4",
    "glm4.5",
    "glm5",
    "kimi-k2",
    "minimax-m2",
    "step3",
    "mimo-v2",
    "internlm2.5",
    "baichuan2:7b",
    "baichuan2:13b",
    "minicpm-v",
    "smollm2:135m",
    "smollm2:360m",
    "smollm2:1.7b",
    "granite3.3:2b",
    "granite3.3:8b",
    "command-r",
    "command-r-plus",
    "starcoder2:3b",
    "starcoder2:7b",
    "starcoder2:15b",
    "codellama:7b",
    "codellama:13b",
    "codellama:34b",
    "dolphin-mixtral",
    "openchat",
    "neural-chat",
    "orca-mini",
    "zephyr",
    "solar",
    "nous-hermes2",
    "wizardlm2",
    "vicuna",
    "rwkv",
    "pythia",
    "dolly-v2",
    "stablelm",
    "redpajama",
    "openllama",
    "mpt",
    "dbrx",
    "arctic",
    "bloom",
    "bloomz",
    "mamba",
    "custom-model",
)

_HF_OPEN_SOURCE_MODELS = (
    "Qwen/Qwen3-0.6B",
    "Qwen/Qwen3-1.7B",
    "Qwen/Qwen3-4B",
    "Qwen/Qwen3-8B",
    "Qwen/Qwen3-14B",
    "Qwen/Qwen3-32B",
    "Qwen/Qwen3-30B-A3B",
    "Qwen/Qwen2.5-0.5B-Instruct",
    "Qwen/Qwen2.5-1.5B-Instruct",
    "Qwen/Qwen2.5-3B-Instruct",
    "Qwen/Qwen2.5-7B-Instruct",
    "Qwen/Qwen2.5-14B-Instruct",
    "Qwen/Qwen2.5-32B-Instruct",
    "Qwen/Qwen2.5-72B-Instruct",
    "Qwen/Qwen2.5-Coder-1.5B-Instruct",
    "Qwen/Qwen2.5-Coder-7B-Instruct",
    "Qwen/Qwen2.5-Coder-14B-Instruct",
    "Qwen/Qwen2.5-Coder-32B-Instruct",
    "Qwen/QwQ-32B",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "google-t5/t5-small",
    "google-t5/t5-base",
    "google-t5/t5-large",
    "google/flan-t5-small",
    "google/flan-t5-base",
    "google/flan-t5-large",
    "google/flan-t5-xl",
    "google/flan-t5-xxl",
    "RWKV/rwkv-4-world",
    "RWKV/rwkv-5-world",
    "RWKV/rwkv-6-world",
    "BlinkDL/rwkv-7-world",
    "EleutherAI/gpt-neox-20b",
    "EleutherAI/gpt-j-6b",
    "EleutherAI/gpt-neo-2.7B",
    "yandex/yalm-100b",
    "meta-llama/Llama-3.3-70B-Instruct",
    "meta-llama/Llama-3.1-8B-Instruct",
    "meta-llama/Llama-3.1-70B-Instruct",
    "meta-llama/Llama-3.2-1B-Instruct",
    "meta-llama/Llama-3.2-3B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "mistralai/Mistral-Nemo-Instruct-2407",
    "mistralai/Mixtral-8x7B-Instruct-v0.1",
    "mistralai/Mixtral-8x22B-Instruct-v0.1",
    "mistralai/Codestral-22B-v0.1",
    "deepseek-ai/DeepSeek-R1",
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B",
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
    "deepseek-ai/deepseek-coder-6.7b-instruct",
    "deepseek-ai/DeepSeek-Coder-V2-Instruct",
    "google/gemma-3-1b-it",
    "google/gemma-3-4b-it",
    "google/gemma-3-12b-it",
    "google/gemma-3-27b-it",
    "google/gemma-2-2b-it",
    "google/gemma-2-9b-it",
    "google/gemma-2-27b-it",
    "microsoft/phi-4",
    "microsoft/Phi-4-mini-instruct",
    "microsoft/Phi-3.5-mini-instruct",
    "tiiuae/Falcon3-1B-Instruct",
    "tiiuae/Falcon3-3B-Instruct",
    "tiiuae/Falcon3-7B-Instruct",
    "tiiuae/Falcon3-10B-Instruct",
    "tiiuae/falcon-180B-chat",
    "01-ai/Yi-6B-Chat",
    "01-ai/Yi-9B-Chat",
    "01-ai/Yi-34B-Chat",
    "THUDM/glm-4-9b-chat",
    "internlm/internlm2_5-7b-chat",
    "internlm/internlm2_5-20b-chat",
    "baichuan-inc/Baichuan2-7B-Chat",
    "baichuan-inc/Baichuan2-13B-Chat",
    "openbmb/MiniCPM3-4B",
    "HuggingFaceTB/SmolLM2-135M-Instruct",
    "HuggingFaceTB/SmolLM2-360M-Instruct",
    "HuggingFaceTB/SmolLM2-1.7B-Instruct",
    "ibm-granite/granite-3.3-2b-instruct",
    "ibm-granite/granite-3.3-8b-instruct",
    "CohereForAI/c4ai-command-r-v01",
    "CohereForAI/c4ai-command-r-plus",
    "CohereForAI/aya-23-8B",
    "CohereForAI/aya-23-35B",
    "bigscience/bloomz-7b1",
    "bigscience/bloom",
    "mosaicml/mpt-7b-instruct",
    "mosaicml/mpt-30b-instruct",
    "databricks/dbrx-instruct",
    "ai21labs/Jamba-v0.1",
    "Nexusflow/Starling-LM-7B-beta",
    "HuggingFaceH4/zephyr-7b-beta",
    "NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO",
    "openchat/openchat-3.5-0106",
    "WizardLMTeam/WizardLM-2-8x22B",
    "lmsys/vicuna-13b-v1.5",
    "codellama/CodeLlama-7b-Instruct-hf",
    "codellama/CodeLlama-13b-Instruct-hf",
    "codellama/CodeLlama-34b-Instruct-hf",
    "bigcode/starcoder2-3b",
    "bigcode/starcoder2-7b",
    "bigcode/starcoder2-15b",
    "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF",
)

_LINKED_SOURCE_OPEN_SOURCE_MODELS = (
    "google/flan-ul2",
    "allenai/OLMo-7B-Instruct",
    "allenai/OLMo-2-1124-7B-Instruct",
    "allenai/OLMo-2-1124-13B-Instruct",
    "cerebras/Cerebras-GPT-111M",
    "cerebras/Cerebras-GPT-256M",
    "cerebras/Cerebras-GPT-590M",
    "cerebras/Cerebras-GPT-1.3B",
    "cerebras/Cerebras-GPT-2.7B",
    "cerebras/Cerebras-GPT-6.7B",
    "cerebras/Cerebras-GPT-13B",
    "OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5",
    "EleutherAI/pythia-70m",
    "EleutherAI/pythia-160m",
    "EleutherAI/pythia-410m",
    "EleutherAI/pythia-1b",
    "EleutherAI/pythia-1.4b",
    "EleutherAI/pythia-2.8b",
    "EleutherAI/pythia-6.9b",
    "EleutherAI/pythia-12b",
    "databricks/dolly-v2-3b",
    "databricks/dolly-v2-7b",
    "databricks/dolly-v2-12b",
    "stabilityai/stablelm-base-alpha-3b",
    "stabilityai/stablelm-base-alpha-7b",
    "stabilityai/stablelm-tuned-alpha-3b",
    "stabilityai/stablelm-tuned-alpha-7b",
    "lmsys/fastchat-t5-3b-v1.0",
    "aisquared/dlite-v2-1_5b",
    "h2oai/h2ogpt-oasst1-512-12b",
    "togethercomputer/RedPajama-INCITE-7B-Instruct",
    "openlm-research/open_llama_3b",
    "openlm-research/open_llama_7b",
    "openlm-research/open_llama_13b",
    "mosaicml/mpt-7b-chat",
    "mosaicml/mpt-7b-storywriter",
    "mosaicml/mpt-30b-chat",
    "nomic-ai/gpt4all-j",
    "Salesforce/xgen-7b-8k-inst",
    "inceptionai/jais-13b-chat",
    "codellama/CodeLlama-70b-Instruct-hf",
    "teknium/OpenHermes-2.5-Mistral-7B",
    "apple/OpenELM-270M-Instruct",
    "apple/OpenELM-450M-Instruct",
    "apple/OpenELM-1_1B-Instruct",
    "apple/OpenELM-3B-Instruct",
    "Deci/DeciLM-7B-instruct",
    "THUDM/chatglm-6b",
    "THUDM/chatglm2-6b",
    "THUDM/chatglm3-6b",
    "THUDM/glm-4-9b-chat",
    "Skywork/Skywork-13B-base",
    "LLM360/Amber",
    "Cerebras/FLOR-6.3B",
    "Qwen/Qwen1.5-0.5B-Chat",
    "Qwen/Qwen1.5-1.8B-Chat",
    "Qwen/Qwen1.5-4B-Chat",
    "Qwen/Qwen1.5-7B-Chat",
    "Qwen/Qwen1.5-14B-Chat",
    "Qwen/Qwen1.5-32B-Chat",
    "Qwen/Qwen1.5-72B-Chat",
    "Qwen/Qwen1.5-110B-Chat",
    "Qwen/Qwen1.5-MoE-A2.7B-Chat",
    "LargeWorldModel/LWM-Text-1M",
    "YerevaNN/YerevaNN-Grok-1",
    "state-spaces/mamba-130m",
    "state-spaces/mamba-370m",
    "state-spaces/mamba-790m",
    "state-spaces/mamba-1.4b",
    "state-spaces/mamba-2.8b",
    "Snowflake/snowflake-arctic-instruct",
    "Fugaku-LLM/Fugaku-LLM-13B-instruct",
    "tiiuae/Falcon2-11B",
    "01-ai/Yi-1.5-6B-Chat",
    "01-ai/Yi-1.5-9B-Chat",
    "01-ai/Yi-1.5-34B-Chat",
    "deepseek-ai/DeepSeek-V2-Lite-Chat",
    "deepseek-ai/DeepSeek-V2-Chat",
    "deepseek-ai/DeepSeek-V3",
    "deepseek-ai/DeepSeek-V3-0324",
    "deepseek-ai/DeepSeek-V3.1",
    "deepseek-ai/DeepSeek-V3.2",
    "deepseek-ai/DeepSeek-R1-0528",
    "microsoft/Phi-3-medium-128k-instruct",
    "microsoft/Phi-3-mini-128k-instruct",
    "microsoft/phi-4-reasoning",
    "yulan-team/YuLan-Mini",
    "AtlaAI/Selene-1-Mini-Llama-3.1-8B",
    "bigcode/santacoder",
    "Salesforce/codegen2-1B",
    "Salesforce/codegen2-3_7B",
    "Salesforce/codegen2-7B",
    "HuggingFaceH4/starchat-alpha",
    "replit/replit-code-v1-3b",
    "Salesforce/codet5p-770m",
    "Salesforce/codet5p-2b",
    "Salesforce/codet5p-6b",
    "Salesforce/codegen25-7b-multi",
    "Deci/DeciCoder-1b",
    "meta-llama/Llama-2-7b-chat-hf",
    "meta-llama/Llama-2-13b-chat-hf",
    "meta-llama/Llama-2-70b-chat-hf",
    "meta-llama/Llama-3-8B-Instruct",
    "meta-llama/Llama-3-70B-Instruct",
    "meta-llama/Llama-4-Maverick-17B-128E-Instruct",
    "meta-llama/Llama-4-Scout-17B-16E-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.2",
    "mistralai/Mistral-Large-Instruct-2407",
    "mistralai/Mistral-Large-Instruct-2411",
    "Qwen/Qwen2-72B-Instruct",
    "Qwen/Qwen3-235B-A22B-Instruct-2507",
    "Qwen/Qwen3-235B-A22B-Thinking-2507",
    "Qwen/Qwen3-VL-235B-A22B-Instruct",
    "Qwen/Qwen3.5",
    "Qwen/Qwen3.5-30B-A3B",
    "Qwen/Qwen3.5-Coder",
    "zai-org/GLM-4.5",
    "zai-org/GLM-4.5-Air",
    "zai-org/GLM-4.6",
    "zai-org/GLM-5",
    "moonshotai/Kimi-K2",
    "moonshotai/Kimi-K2-Thinking",
    "moonshotai/Kimi-K2.5",
    "MiniMaxAI/MiniMax-M2.5",
    "stepfun-ai/Step3",
    "stepfun-ai/Step-3.5-Flash",
    "XiaomiMiMo/MiMo-V2-Flash",
    "google/gemma-4-4b-it",
    "google/gemma-4-12b-it",
    "google/gemma-4-27b-it",
    "nvidia/Llama-3.1-Nemotron-Ultra-253B-v1",
    "nvidia/Llama-3.1-Nemotron-Super-49B-v1",
    "nvidia/Llama-3.1-Nemotron-Nano-8B-v1",
)


def _unique_model_suggestions(*groups: tuple[str, ...]) -> tuple[str, ...]:
    values: list[str] = []
    for group in groups:
        for item in group:
            text = str(item or "").strip()
            if text and text not in values:
                values.append(text)
    return tuple(values)

_PROVIDER_SPECS: tuple[LLMProviderSpec, ...] = (
    LLMProviderSpec(
        key="openai",
        label="OpenAI / ChatGPT",
        mode="cloud",
        protocol=OPENAI_COMPATIBLE_PROTOCOL,
        default_base_url="https://api.openai.com/v1",
        default_model="gpt-5.5",
        api_key_env="OPENAI_API_KEY",
        model_suggestions=(
            "gpt-5.6",
            "gpt-5.6-sol",
            "gpt-5.6-terra",
            "gpt-5.6-luna",
            "gpt-5.5",
            "gpt-5.5-2026-04-23",
            "gpt-5.5-pro",
            "gpt-5.5-pro-2026-04-23",
            "gpt-5.4",
            "gpt-5.4-2026-03-05",
            "gpt-5.4-pro",
            "gpt-5.4-pro-2026-03-05",
            "gpt-5.4-mini",
            "gpt-5.4-mini-2026-03-17",
            "gpt-5.4-nano",
            "gpt-5.4-nano-2026-03-17",
            "gpt-5.3-chat-latest",
            "gpt-5.3-codex",
            "gpt-5.2",
            "gpt-5.2-codex",
            "gpt-5.2-chat-latest",
            "gpt-5.2-pro",
            "gpt-5.1",
            "gpt-5-codex",
            "gpt-5-mini",
            "gpt-5-nano",
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
        ),
        reasoning_efforts=_OPENAI_REASONING_EFFORTS,
        notes=(
            "Uses the OpenAI-compatible chat completions endpoint.",
            "GPT-5.6 Sol, Terra, and Luna support reasoning levels through max; availability depends on the API account.",
        ),
    ),
    LLMProviderSpec(
        key="anthropic",
        label="Anthropic Claude",
        mode="cloud",
        protocol=ANTHROPIC_MESSAGES_PROTOCOL,
        default_base_url="https://api.anthropic.com",
        default_model="claude-sonnet-4-5-20250929",
        api_key_env="ANTHROPIC_API_KEY",
        model_suggestions=(
            "claude-sonnet-4-5-20250929",
            "claude-haiku-4-5-20251001",
            "claude-opus-4-5-20251101",
            "claude-opus-4-1-20250805",
            "claude-opus-4-20250514",
            "claude-sonnet-4-20250514",
            "claude-sonnet-4-5",
            "claude-haiku-4-5",
            "claude-opus-4-5",
            "claude-opus-4-1",
            "claude-opus-4-0",
            "claude-sonnet-4-0",
        ),
        reasoning_efforts=("default", "disabled", "enabled", "low", "medium", "high"),
        notes=("Uses the Anthropic messages endpoint with the 2023-06-01 API version header.",),
    ),
    LLMProviderSpec(
        key="gemini",
        label="Google Gemini",
        mode="cloud",
        protocol=GEMINI_GENERATE_CONTENT_PROTOCOL,
        default_base_url="https://generativelanguage.googleapis.com/v1beta",
        default_model="gemini-3-flash-preview",
        api_key_env="GEMINI_API_KEY",
        model_suggestions=(
            "gemini-3.1-pro-preview",
            "gemini-3.1-pro-preview-customtools",
            "gemini-3-flash-preview",
            "gemini-3.1-flash-lite-preview",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-preview-09-2025",
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash-lite-preview-09-2025",
        ),
        reasoning_efforts=("default", "minimal", "low", "medium", "high"),
        notes=("Uses the Gemini generateContent endpoint.",),
    ),
    LLMProviderSpec(
        key="deepseek",
        label="DeepSeek",
        mode="cloud",
        protocol=OPENAI_COMPATIBLE_PROTOCOL,
        default_base_url="https://api.deepseek.com",
        default_model="deepseek-v4-flash",
        api_key_env="DEEPSEEK_API_KEY",
        model_suggestions=("deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"),
        reasoning_efforts=("default", "disabled", "enabled", "high", "max"),
        notes=("DeepSeek documents an OpenAI-compatible chat completions surface.",),
    ),
    LLMProviderSpec(
        key="mistral",
        label="Mistral AI",
        mode="cloud",
        protocol=OPENAI_COMPATIBLE_PROTOCOL,
        default_base_url="https://api.mistral.ai/v1",
        default_model="mistral-small-latest",
        api_key_env="MISTRAL_API_KEY",
        model_suggestions=(
            "mistral-large-latest",
            "mistral-medium-latest",
            "mistral-small-latest",
            "codestral-latest",
            "open-mistral-nemo",
        ),
        reasoning_efforts=("default", "low", "medium", "high"),
        notes=("Mistral exposes an OpenAI-compatible chat completions API.",),
    ),
    LLMProviderSpec(
        key="grok",
        label="xAI Grok",
        mode="cloud",
        protocol=OPENAI_COMPATIBLE_PROTOCOL,
        default_base_url="https://api.x.ai/v1",
        default_model="grok-4.3",
        api_key_env="XAI_API_KEY",
        model_suggestions=(
            "grok-4.3",
            "grok-4.3-latest",
            "grok-4.20",
            "grok-4.20-reasoning",
            "grok-4.20-non-reasoning",
            "grok-4-fast-reasoning",
            "grok-4-fast-non-reasoning",
        ),
        reasoning_efforts=("default", "low", "medium", "high"),
        notes=("xAI documents OpenAI-compatible chat completions at /v1/chat/completions.",),
    ),
    LLMProviderSpec(
        key="qwen",
        label="Alibaba Qwen / DashScope",
        mode="cloud",
        protocol=OPENAI_COMPATIBLE_PROTOCOL,
        default_base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        default_model="qwen3.6-plus",
        api_key_env="DASHSCOPE_API_KEY",
        model_suggestions=(
            "qwen3.7-max",
            "qwen3.7-max-2026-06-08",
            "qwen3.7-max-2026-05-20",
            "qwen3.6-max-preview",
            "qwen3.6-plus",
            "qwen3.6-plus-2026-04-02",
            "qwen3.6-flash",
            "qwen3.6-flash-2026-04-16",
            "qwen3-max",
            "qwen3-max-2026-01-23",
            "qwen3-max-2025-09-23",
            "qwen3-max-preview",
            "qwen3.5-plus",
            "qwen3.5-plus-2026-02-15",
            "qwen3.5-flash",
            "qwen3.5-flash-2026-02-23",
            "qwen3-coder-plus",
            "qwen3-coder-flash",
            "qwen-plus-us",
            "qwen-flash-us",
        ),
        reasoning_efforts=("default", "disabled", "enabled", "low", "medium", "high", "max"),
        notes=(
            "DashScope provides OpenAI-compatible endpoints for Qwen models.",
            "The request uses enable_thinking for compatible Qwen chat models; Qwen 3.5/3.6 multimodal and Responses-only features require DashScope's corresponding API surface.",
        ),
    ),
    LLMProviderSpec(
        key="moonshot",
        label="Moonshot AI / Kimi",
        mode="cloud",
        protocol=OPENAI_COMPATIBLE_PROTOCOL,
        default_base_url="https://api.moonshot.ai/v1",
        default_model="kimi-k3",
        api_key_env="MOONSHOT_API_KEY",
        model_suggestions=(
            "kimi-k3",
            "kimi-k2.7-code",
            "kimi-k2.7-code-highspeed",
            "kimi-k2.6",
            "kimi-k2.5",
        ),
        reasoning_efforts=("default", "disabled", "enabled", "max"),
        notes=(
            "Uses Moonshot's OpenAI-compatible /v1/chat/completions endpoint.",
            "Kimi K3 supports reasoning_effort=max. Kimi K2.5 and K2.6 use thinking enabled or disabled; K2.7 Code always reasons.",
            "Use the provider model discovery endpoint or the editable model field for account-specific releases.",
        ),
    ),
    LLMProviderSpec(
        key="local",
        label="Local / Custom OpenAI-Compatible",
        mode="local",
        protocol=OPENAI_COMPATIBLE_PROTOCOL,
        default_base_url="http://127.0.0.1:11434/v1",
        default_model="qwen3:8b",
        api_key_env="LOCAL_LLM_API_KEY",
        model_suggestions=_unique_model_suggestions(
            _OLLAMA_OPEN_SOURCE_MODELS,
            _HF_OPEN_SOURCE_MODELS,
            _LINKED_SOURCE_OPEN_SOURCE_MODELS,
        ),
        reasoning_efforts=_OPEN_SOURCE_REASONING_EFFORTS,
        notes=(
            "Use this for any local, LAN, private IP, or custom OpenAI-compatible endpoint.",
            "The model field is intentionally editable so arbitrary Ollama, GGUF, or Hugging Face IDs can be used.",
        ),
    ),
    LLMProviderSpec(
        key="ollama",
        label="Ollama",
        mode="local",
        protocol=OPENAI_COMPATIBLE_PROTOCOL,
        default_base_url="http://127.0.0.1:11434/v1",
        default_model="qwen3:8b",
        api_key_env="OLLAMA_API_KEY",
        model_suggestions=_OLLAMA_OPEN_SOURCE_MODELS,
        reasoning_efforts=_OPEN_SOURCE_REASONING_EFFORTS,
        notes=(
            "Ollama exposes OpenAI-compatible /v1/chat/completions and /v1/models endpoints.",
            "Automatic download/start/remove actions are available for localhost Ollama.",
        ),
    ),
    LLMProviderSpec(
        key="vllm",
        label="vLLM / SGLang",
        mode="local",
        protocol=OPENAI_COMPATIBLE_PROTOCOL,
        default_base_url="http://127.0.0.1:8000/v1",
        default_model="Qwen/Qwen3-8B",
        api_key_env="VLLM_API_KEY",
        model_suggestions=_unique_model_suggestions(_HF_OPEN_SOURCE_MODELS, _LINKED_SOURCE_OPEN_SOURCE_MODELS),
        reasoning_efforts=_OPEN_SOURCE_REASONING_EFFORTS,
        notes=(
            "Use this for self-hosted vLLM or SGLang OpenAI-compatible servers.",
            "Set Base URL / IP to a LAN, private, or remote /v1 endpoint.",
        ),
    ),
    LLMProviderSpec(
        key="llamacpp",
        label="llama.cpp server",
        mode="local",
        protocol=OPENAI_COMPATIBLE_PROTOCOL,
        default_base_url="http://127.0.0.1:8080/v1",
        default_model="local-model",
        api_key_env="LLAMACPP_API_KEY",
        model_suggestions=_unique_model_suggestions(
            (
                "local-model",
                "qwen3-8b-q4_k_m.gguf",
                "llama-3.1-8b-instruct-q4_k_m.gguf",
                "mistral-7b-instruct-q4_k_m.gguf",
                "gemma-3-4b-it-q4_k_m.gguf",
            ),
            _OLLAMA_OPEN_SOURCE_MODELS,
            _LINKED_SOURCE_OPEN_SOURCE_MODELS,
        ),
        reasoning_efforts=_OPEN_SOURCE_REASONING_EFFORTS,
        notes=(
            "Use this for llama.cpp server; the loaded model name is often reported by /v1/models.",
            "GGUF filenames are accepted as editable model IDs when your server exposes them.",
        ),
    ),
    LLMProviderSpec(
        key="lmstudio",
        label="LM Studio",
        mode="local",
        protocol=OPENAI_COMPATIBLE_PROTOCOL,
        default_base_url="http://127.0.0.1:1234/v1",
        default_model="local-model",
        api_key_env="LMSTUDIO_API_KEY",
        model_suggestions=_unique_model_suggestions(
            ("local-model",),
            _HF_OPEN_SOURCE_MODELS,
            _LINKED_SOURCE_OPEN_SOURCE_MODELS,
        ),
        reasoning_efforts=_OPEN_SOURCE_REASONING_EFFORTS,
        notes=(
            "Use this for LM Studio local server or a remote LM Studio-compatible /v1 endpoint.",
            "The model field is editable because LM Studio exposes locally downloaded model IDs.",
        ),
    ),
    LLMProviderSpec(
        key="tgi",
        label="Hugging Face TGI",
        mode="local",
        protocol=OPENAI_COMPATIBLE_PROTOCOL,
        default_base_url="http://127.0.0.1:3000/v1",
        default_model="tgi",
        api_key_env="HUGGINGFACE_API_KEY",
        model_suggestions=_unique_model_suggestions(
            ("tgi",),
            _HF_OPEN_SOURCE_MODELS,
            _LINKED_SOURCE_OPEN_SOURCE_MODELS,
        ),
        reasoning_efforts=_OPEN_SOURCE_REASONING_EFFORTS,
        notes=(
            "Use this for Hugging Face Text Generation Inference Messages API endpoints.",
            "Remote Hugging Face Inference Endpoints should include /v1 in the base URL.",
        ),
    ),
    LLMProviderSpec(
        key="open-source",
        label="Generic Open-Source / Remote",
        mode="local",
        protocol=OPENAI_COMPATIBLE_PROTOCOL,
        default_base_url="http://127.0.0.1:8000/v1",
        default_model="Qwen/Qwen3-8B",
        api_key_env="OPEN_SOURCE_LLM_API_KEY",
        model_suggestions=_unique_model_suggestions(
            _HF_OPEN_SOURCE_MODELS,
            _LINKED_SOURCE_OPEN_SOURCE_MODELS,
            _OLLAMA_OPEN_SOURCE_MODELS,
        ),
        reasoning_efforts=_OPEN_SOURCE_REASONING_EFFORTS,
        notes=(
            "Use this for any OpenAI-compatible open-source runtime, including remote IP or URL endpoints.",
            "For public endpoints, enable Allow public network endpoint so context is minimized.",
        ),
    ),
)

_PROVIDER_BY_KEY = {provider.key: provider for provider in _PROVIDER_SPECS}
_PROVIDER_ALIASES = {
    "": "openai",
    "chatgpt": "openai",
    "openai-chatgpt": "openai",
    "claude": "anthropic",
    "anthropic-claude": "anthropic",
    "google": "gemini",
    "google-gemini": "gemini",
    "mistral-ai": "mistral",
    "xai": "grok",
    "xai-grok": "grok",
    "dashscope": "qwen",
    "alibaba": "qwen",
    "alibaba-qwen": "qwen",
    "ollama": "ollama",
    "open-source": "open-source",
    "opensource": "open-source",
    "open-weight": "open-source",
    "open-weights": "open-source",
    "oss": "open-source",
    "huggingface": "open-source",
    "hugging-face": "open-source",
    "hf": "open-source",
    "qwen-local": "open-source",
    "t5": "open-source",
    "flan-t5": "open-source",
    "rwkv": "open-source",
    "rmkv": "open-source",
    "gpt20b": "open-source",
    "gpt-neox": "open-source",
    "yalm": "open-source",
    "glm": "open-source",
    "glm5": "open-source",
    "chatglm": "open-source",
    "zai": "open-source",
    "kimi": "moonshot",
    "moonshot-ai": "moonshot",
    "minimax": "open-source",
    "step": "open-source",
    "stepfun": "open-source",
    "mimo": "open-source",
    "xiaomi": "open-source",
    "olmo": "open-source",
    "dbrx": "open-source",
    "redpajama": "open-source",
    "openllama": "open-source",
    "open-llama": "open-source",
    "pythia": "open-source",
    "cerebras": "open-source",
    "dolly": "open-source",
    "stablelm": "open-source",
    "mamba": "open-source",
    "xgen": "open-source",
    "jais": "open-source",
    "arctic": "open-source",
    "fugaku": "open-source",
    "nemotron": "open-source",
    "gemma4": "open-source",
    "llama4": "open-source",
    "llama-4": "open-source",
    "bloom": "open-source",
    "bloomz": "open-source",
    "mpt": "open-source",
    "santacoder": "open-source",
    "starchat": "open-source",
    "replit-code": "open-source",
    "codet5": "open-source",
    "decicoder": "open-source",
    "vllm": "vllm",
    "s-glang": "vllm",
    "sglang": "vllm",
    "llama-cpp": "llamacpp",
    "llama.cpp": "llamacpp",
    "llamacpp": "llamacpp",
    "llama-cpp-server": "llamacpp",
    "lm-studio": "lmstudio",
    "lmstudio": "lmstudio",
    "text-generation-inference": "tgi",
    "huggingface-tgi": "tgi",
    "hf-tgi": "tgi",
    "local-openai": "local",
    "local-openai-compatible": "local",
    "custom": "local",
}


def llm_provider_choices() -> dict[str, str]:
    choices = {provider.key: provider.key for provider in _PROVIDER_SPECS}
    choices.update(_PROVIDER_ALIASES)
    return dict(sorted(choices.items()))


_LLM_CONFIG_KEYS = {
    "llm_enabled",
    "llm_provider",
    "llm_model",
    "llm_base_url",
    "llm_api_key",
    "llm_api_key_env",
    "llm_use_for",
    "llm_allow_public_network",
    "llm_reasoning_effort",
}


def _coerce_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "off", "disabled"}:
        return False
    return bool(default)


def normalize_llm_provider_key(value: str | None) -> str:
    raw_key = str(value or "").strip().lower().replace("_", "-")
    normalized = _PROVIDER_ALIASES.get(raw_key, raw_key)
    return normalized if normalized in _PROVIDER_BY_KEY else "openai"


def llm_provider_spec_for_key(value: str | None) -> LLMProviderSpec:
    return _PROVIDER_BY_KEY[normalize_llm_provider_key(value)]


def _extra_model_suggestions(provider_key: str) -> tuple[str, ...]:
    env_name = f"BOT_LLM_EXTRA_MODELS_{str(provider_key or '').upper().replace('-', '_')}"
    raw = str(os.environ.get(env_name) or "").strip()
    if not raw:
        return ()
    values = []
    for item in raw.replace(";", ",").split(","):
        text = item.strip()
        if text and text not in values:
            values.append(text)
    return tuple(values)


def _catalog_path() -> Path:
    raw = str(os.environ.get(LLM_MODEL_CATALOG_PATH_ENV) or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path("~/.trading-bot/llm-models.json").expanduser()


def _file_model_suggestions(provider_key: str) -> tuple[str, ...]:
    path = _catalog_path()
    if not path.is_file():
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, dict):
        return ()
    raw_models = payload.get(provider_key)
    if raw_models is None:
        raw_models = payload.get("providers", {}).get(provider_key) if isinstance(payload.get("providers"), dict) else None
    if not isinstance(raw_models, list):
        return ()
    values: list[str] = []
    for item in raw_models:
        text = str(item or "").strip()
        if text and text not in values:
            values.append(text)
    return tuple(values)


def _model_suggestions_for_provider(provider: LLMProviderSpec) -> list[str]:
    suggestions = list(provider.model_suggestions)
    for model in _extra_model_suggestions(provider.key):
        if model not in suggestions:
            suggestions.append(model)
    for model in _file_model_suggestions(provider.key):
        if model not in suggestions:
            suggestions.append(model)
    return suggestions


def list_llm_provider_specs() -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    for provider in _PROVIDER_SPECS:
        payload = provider.to_dict()
        payload["model_suggestions"] = _model_suggestions_for_provider(provider)
        payload["catalog_revision"] = LLM_PROVIDER_CATALOG_REVISION
        payload["custom_models_env"] = f"BOT_LLM_EXTRA_MODELS_{provider.key.upper().replace('-', '_')}"
        payload["custom_models_path_env"] = LLM_MODEL_CATALOG_PATH_ENV
        payload["catalog_path"] = str(_catalog_path())
        payload["catalog_note"] = (
            "Static defaults can drift; add local overrides with custom_models_env or custom_models_path_env."
        )
        specs.append(payload)
    return specs


def _masked_key_present(config: dict[str, object], env_name: str) -> bool:
    inline_key = str(config.get("llm_api_key") or "").strip()
    env_key = str(os.environ.get(env_name) or "").strip()
    return bool(inline_key or env_key)


def _normalize_reasoning_effort(provider: LLMProviderSpec, value: object) -> str:
    raw_value = str(value or "").strip().lower().replace("_", "-")
    efforts = tuple(str(item).strip().lower() for item in provider.reasoning_efforts if str(item).strip())
    if not efforts:
        return "default"
    default_effort = str(provider.default_reasoning_effort or efforts[0]).strip().lower() or efforts[0]
    aliases = {
        "": default_effort,
        "auto": "default",
        "off": "none" if "none" in efforts else "disabled",
        "no": "none" if "none" in efforts else "disabled",
        "false": "none" if "none" in efforts else "disabled",
        "extra-high": "xhigh",
        "extra_high": "xhigh",
    }
    normalized = aliases.get(raw_value, raw_value)
    return normalized if normalized in efforts else default_effort


def build_llm_config_payload(config: dict | None) -> dict[str, object]:
    cfg = config if isinstance(config, dict) else {}
    provider = llm_provider_spec_for_key(str(cfg.get("llm_provider") or "openai"))
    api_key_env = str(cfg.get("llm_api_key_env") or provider.api_key_env).strip() or provider.api_key_env
    base_url = str(cfg.get("llm_base_url") or provider.default_base_url).strip() or provider.default_base_url
    model = str(cfg.get("llm_model") or provider.default_model).strip()
    reasoning_effort = _normalize_reasoning_effort(provider, cfg.get("llm_reasoning_effort"))
    return {
        "enabled": _coerce_bool(cfg.get("llm_enabled"), False),
        "provider": provider.key,
        "provider_label": provider.label,
        "mode": provider.mode,
        "protocol": provider.protocol,
        "catalog_revision": LLM_PROVIDER_CATALOG_REVISION,
        "catalog_path": str(_catalog_path()),
        "custom_models_env": f"BOT_LLM_EXTRA_MODELS_{provider.key.upper().replace('-', '_')}",
        "custom_models_path_env": LLM_MODEL_CATALOG_PATH_ENV,
        "model": model,
        "base_url": base_url,
        "api_key_env": api_key_env,
        "api_key_present": _masked_key_present(cfg, api_key_env),
        "use_for": str(cfg.get("llm_use_for") or "advisory").strip() or "advisory",
        "allow_public_network": _coerce_bool(cfg.get("llm_allow_public_network"), False),
        "reasoning_effort": reasoning_effort,
        "default_reasoning_effort": provider.default_reasoning_effort,
        "reasoning_efforts": list(provider.reasoning_efforts),
        "model_suggestions": _model_suggestions_for_provider(provider),
        "notes": list(provider.notes),
        "execution_policy": {
            "advisory_only": True,
            "can_execute_orders": False,
            "owner": "strategy_and_risk_runtime",
        },
    }


def update_llm_config(config: dict | None, patch: dict | None) -> dict[str, object]:
    updated = copy.deepcopy(config if isinstance(config, dict) else {})
    values = patch if isinstance(patch, dict) else {}
    for key, value in values.items():
        if key not in _LLM_CONFIG_KEYS:
            continue
        if key == "llm_provider":
            updated[key] = normalize_llm_provider_key(str(value or ""))
        elif key in {"llm_enabled", "llm_allow_public_network"}:
            updated[key] = _coerce_bool(value, False)
        elif key == "llm_reasoning_effort":
            provider = llm_provider_spec_for_key(str(updated.get("llm_provider") or "openai"))
            updated[key] = _normalize_reasoning_effort(provider, value)
        elif key == "llm_api_key" and str(value or "").strip() in {"", "********"}:
            updated.pop(key, None)
        else:
            updated[key] = str(value or "").strip()
    if "llm_provider" not in updated:
        updated["llm_provider"] = "openai"
    if "llm_reasoning_effort" in updated:
        provider = llm_provider_spec_for_key(str(updated.get("llm_provider") or "openai"))
        updated["llm_reasoning_effort"] = _normalize_reasoning_effort(provider, updated.get("llm_reasoning_effort"))
    return updated
