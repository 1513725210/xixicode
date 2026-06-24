"""Config — 配置管理模块。

参考 MiniCode config.ts 的多源配置加载 + 合并模式。
配置源优先级（从低到高）：
  1. 默认值
  2. ~/.minicode/config.yaml（用户级）
  3. .minicode/config.yaml（项目级）
  4. 环境变量

RuntimeConfig 是最终解析后的扁平配置，供各模块使用。
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


# ── 路径常量 ──

MINICODE_HOME = os.environ.get(
    "MINICODE_HOME",
    str(Path.home() / ".minicode"),
)
MINICODE_USER_CONFIG = os.path.join(MINICODE_HOME, "config.yaml")
MINICODE_PROJECT_CONFIG = ".minicode/config.yaml"


# ── 配置结构 ──


@dataclass
class LLMBackendConfig:
    """单个 LLM 后端的配置。"""
    base_url: str = ""
    api_key: str = ""
    models: list[str] = field(default_factory=list)


@dataclass
class RuntimeConfig:
    """运行时使用的扁平配置。

    所有值已从多源合并解析完毕，直接使用。
    """

    # LLM
    default_model: str = "deepseek-chat"
    fallback_model: str = ""
    backends: dict[str, LLMBackendConfig] = field(default_factory=dict)

    # Agent
    max_steps: int = 10
    max_tool_output: int = 3000
    dry_run: bool = False
    auto_approve: bool = False

    # Memory
    memory_enabled: bool = True
    memory_top_k: int = 5

    # Security
    security_enabled: bool = True

    # Display
    quiet: bool = False
    verbose: bool = False

    @property
    def active_backend(self) -> LLMBackendConfig | None:
        """获取当前默认模型对应的后端配置。"""
        model = self.default_model
        for backend in self.backends.values():
            if model in backend.models:
                return backend
        # fallback: 返回第一个有 api_key 的后端
        for backend in self.backends.values():
            if backend.api_key:
                return backend
        return None


# ── 默认配置 ──

DEFAULT_CONFIG = {
    "default_model": "deepseek-chat",
    "max_steps": 10,
    "max_tool_output": 3000,
    "memory_enabled": True,
    "memory_top_k": 5,
    "security_enabled": True,
    "backends": {
        "deepseek": {
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "${DEEPSEEK_API_KEY}",
            "models": ["deepseek-chat", "deepseek-reasoner"],
        },
    },
}


# ── 加载函数 ──


def _resolve_env_vars(value: str) -> str:
    """解析字符串中的 ${VAR} 环境变量引用。

    Args:
        value: 可能含 ${VAR} 的字符串

    Returns:
        str: 替换后的字符串
    """
    import re

    def replacer(match):
        var_name = match.group(1)
        return os.environ.get(var_name, "")

    return re.sub(r"\$\{(\w+)\}", replacer, value)


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个字典，override 中的值覆盖 base。"""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _resolve_env_in_config(config: dict) -> dict:
    """递归解析配置中所有的 ${VAR} 引用。"""
    result = {}
    for key, value in config.items():
        if isinstance(value, str):
            result[key] = _resolve_env_vars(value)
        elif isinstance(value, dict):
            result[key] = _resolve_env_in_config(value)
        elif isinstance(value, list):
            result[key] = [
                _resolve_env_vars(v) if isinstance(v, str) else v
                for v in value
            ]
        else:
            result[key] = value
    return result


def load_yaml_config(file_path: str) -> dict:
    """从 YAML 文件加载配置。

    Args:
        file_path: YAML 文件路径

    Returns:
        dict: 解析后的配置字典，文件不存在或解析失败返回空字典
    """
    path = Path(file_path)
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            return {}
        return data
    except (yaml.YAMLError, OSError, UnicodeDecodeError):
        return {}


def load_runtime_config(
    user_config_path: str | None = None,
    project_config_path: str | None = None,
) -> RuntimeConfig:
    """加载并合并所有配置源，返回 RuntimeConfig。

    优先级（从低到高）：默认 < 用户级 < 项目级 < 环境变量

    Args:
        user_config_path: 用户级 YAML 配置文件路径
        project_config_path: 项目级 YAML 配置文件路径

    Returns:
        RuntimeConfig: 解析后的运行时配置
    """
    user_path = user_config_path or MINICODE_USER_CONFIG
    project_path = project_config_path or MINICODE_PROJECT_CONFIG

    # 1. 默认配置
    merged = dict(DEFAULT_CONFIG)

    # 2. 用户级配置
    user_config = load_yaml_config(user_path)
    merged = _deep_merge(merged, user_config)

    # 3. 项目级配置
    project_config = load_yaml_config(project_path)
    merged = _deep_merge(merged, project_config)

    # 4. 解析环境变量引用
    merged = _resolve_env_in_config(merged)

    # 5. 构建 RuntimeConfig
    backends = {}
    for name, cfg in merged.get("backends", {}).items():
        if isinstance(cfg, dict):
            backends[name] = LLMBackendConfig(
                base_url=cfg.get("base_url", ""),
                api_key=cfg.get("api_key", ""),
                models=cfg.get("models", []),
            )

    return RuntimeConfig(
        default_model=merged.get("default_model", "deepseek-chat"),
        fallback_model=merged.get("fallback_model", ""),
        backends=backends,
        max_steps=merged.get("max_steps", 10),
        max_tool_output=merged.get("max_tool_output", 3000),
        dry_run=merged.get("dry_run", False),
        auto_approve=merged.get("auto_approve", False),
        memory_enabled=merged.get("memory_enabled", True),
        memory_top_k=merged.get("memory_top_k", 5),
        security_enabled=merged.get("security_enabled", True),
        quiet=merged.get("quiet", False),
        verbose=merged.get("verbose", False),
    )
