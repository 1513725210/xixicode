"""Session — 会话持久化管理。

参考 MiniCode session.ts 的 JSONL append-only 设计：
- 每个会话一个 .jsonl 文件，存储在 ~/.minicode/projects/<hash>/
- parentUuid 链式结构支持事件树
- 支持 compact boundary 标记
- 会话列表、加载、复制、清理

V1 实现：核心保存/加载/列表，不包含完整的 context collapse 重建。
"""

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from minicode.config import MINICODE_HOME

# ── 路径常量 ──

PROJECTS_DIR = os.path.join(MINICODE_HOME, "projects")
MAX_TITLE_LENGTH = 60


def _project_dir_name(cwd: str) -> str:
    """将工作目录路径转为合法的目录名。"""
    return re.sub(r"[/\\:]+", "-", cwd).strip("-")


def _project_dir(cwd: str) -> str:
    """获取项目会话目录路径。"""
    return os.path.join(PROJECTS_DIR, _project_dir_name(cwd))


def _session_file_path(cwd: str, session_id: str) -> str:
    """获取会话 JSONL 文件路径。"""
    return os.path.join(_project_dir(cwd), f"{session_id}.jsonl")


# ── 数据结构 ──


@dataclass
class SessionEvent:
    """会话中的单个事件。

    Attributes:
        type: 事件类型 (user/assistant/tool_call/tool_result/compact_boundary)
        uuid: 事件唯一 ID
        timestamp: ISO 时间戳
        session_id: 所属会话 ID
        cwd: 工作目录
        parent_uuid: 父事件 UUID（构建事件树）
        content: 事件内容
        metadata: 额外元数据
    """

    type: str
    uuid: str
    timestamp: str
    session_id: str
    cwd: str
    parent_uuid: str | None = None
    content: str = ""
    metadata: dict | None = None


@dataclass
class SessionMeta:
    """会话元数据（列表展示用）。"""

    id: str
    title: str | None
    event_count: int
    updated_at: float


# ── 会话管理 ──


def _ensure_dir(dir_path: str) -> None:
    """确保目录存在。"""
    Path(dir_path).mkdir(parents=True, exist_ok=True)


def _make_event(
    event_type: str,
    content: str,
    session_id: str,
    cwd: str,
    parent_uuid: str | None = None,
    metadata: dict | None = None,
) -> SessionEvent:
    """创建会话事件。"""
    return SessionEvent(
        type=event_type,
        uuid=uuid.uuid4().hex[:12],
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        session_id=session_id,
        cwd=cwd,
        parent_uuid=parent_uuid,
        content=content,
        metadata=metadata,
    )


def _event_to_dict(event: SessionEvent) -> dict:
    """将事件序列化为可 JSON 的字典。"""
    return {
        "type": event.type,
        "uuid": event.uuid,
        "timestamp": event.timestamp,
        "session_id": event.session_id,
        "cwd": event.cwd,
        "parent_uuid": event.parent_uuid,
        "content": event.content,
        "metadata": event.metadata,
    }


def _event_from_dict(data: dict) -> SessionEvent | None:
    """从字典反序列化事件。"""
    try:
        return SessionEvent(
            type=data.get("type", "unknown"),
            uuid=data.get("uuid", ""),
            timestamp=data.get("timestamp", ""),
            session_id=data.get("session_id", ""),
            cwd=data.get("cwd", ""),
            parent_uuid=data.get("parent_uuid"),
            content=data.get("content", ""),
            metadata=data.get("metadata"),
        )
    except (KeyError, TypeError, AttributeError):
        return None


def create_session(cwd: str | None = None) -> str:
    """创建新会话，返回 session_id。

    Args:
        cwd: 工作目录，默认当前目录

    Returns:
        str: 新会话 ID
    """
    cwd = cwd or os.getcwd()
    session_id = uuid.uuid4().hex[:12]

    # 写入初始 system 事件
    system_event = _make_event(
        event_type="system",
        content="MiniCode session started",
        session_id=session_id,
        cwd=cwd,
    )

    _ensure_dir(_project_dir(cwd))
    _append_event(system_event)

    return session_id


def save_event(
    session_id: str,
    event_type: str,
    content: str,
    cwd: str | None = None,
    metadata: dict | None = None,
) -> SessionEvent:
    """向会话追加一个事件。

    Args:
        session_id: 会话 ID
        event_type: 事件类型
        content: 事件内容
        cwd: 工作目录
        metadata: 额外元数据

    Returns:
        SessionEvent: 被保存的事件
    """
    cwd = cwd or os.getcwd()
    file_path = _session_file_path(cwd, session_id)
    last_uuid = _read_last_event_uuid(file_path)

    event = _make_event(
        event_type=event_type,
        content=content,
        session_id=session_id,
        cwd=cwd,
        parent_uuid=last_uuid,
        metadata=metadata,
    )

    _ensure_dir(_project_dir(cwd))
    _append_event(event)

    return event


def save_compact_boundary(
    session_id: str,
    summary_text: str,
    cwd: str | None = None,
    pre_tokens: int = 0,
    post_tokens: int = 0,
) -> None:
    """写入 compact boundary 标记。

    参考 MiniCode 的 compact_boundary 模式：
    在 JSONL 中插入标记事件，后续加载只从最后一个 boundary 开始。

    Args:
        session_id: 会话 ID
        summary_text: 压缩后的摘要
        cwd: 工作目录
        pre_tokens: 压缩前 token 数
        post_tokens: 压缩后 token 数
    """
    cwd = cwd or os.getcwd()
    file_path = _session_file_path(cwd, session_id)
    last_uuid = _read_last_event_uuid(file_path)

    # Boundary 标记
    boundary = _make_event(
        event_type="compact_boundary",
        content="",
        session_id=session_id,
        cwd=cwd,
        parent_uuid=last_uuid,
        metadata={"pre_tokens": pre_tokens, "post_tokens": post_tokens},
    )
    _ensure_dir(_project_dir(cwd))
    _append_event(boundary)

    # Summary 作为 user 消息
    summary = _make_event(
        event_type="user",
        content=summary_text,
        session_id=session_id,
        cwd=cwd,
        parent_uuid=boundary.uuid,
        metadata={"type": "compact_summary"},
    )
    _append_event(summary)


def load_session(
    session_id: str,
    cwd: str | None = None,
    from_last_boundary: bool = True,
) -> list[SessionEvent]:
    """加载会话事件。

    Args:
        session_id: 会话 ID
        cwd: 工作目录
        from_last_boundary: 如果 True，只返回最后一个 compact_boundary 之后的事件

    Returns:
        list[SessionEvent]: 会话事件列表
    """
    cwd = cwd or os.getcwd()
    file_path = _session_file_path(cwd, session_id)

    if not os.path.exists(file_path):
        return []

    events = _read_all_events(file_path)

    if not from_last_boundary:
        return events

    # 找最后一个 compact_boundary
    last_boundary_idx = -1
    for i in range(len(events) - 1, -1, -1):
        if events[i].type == "compact_boundary":
            last_boundary_idx = i
            break

    return events[last_boundary_idx + 1:] if last_boundary_idx >= 0 else events


def list_sessions(cwd: str | None = None) -> list[SessionMeta]:
    """列出当前项目的所有会话。

    Args:
        cwd: 工作目录

    Returns:
        list[SessionMeta]: 按更新时间降序
    """
    cwd = cwd or os.getcwd()
    dir_path = _project_dir(cwd)

    if not os.path.isdir(dir_path):
        return []

    results: list[SessionMeta] = []
    for name in os.listdir(dir_path):
        if not name.endswith(".jsonl"):
            continue
        session_id = name[:-6]  # 去掉 .jsonl
        file_path = os.path.join(dir_path, name)

        try:
            stat = os.stat(file_path)
            events = _read_all_events(file_path)
            title = _extract_title(events)
            results.append(SessionMeta(
                id=session_id,
                title=title,
                event_count=len(events),
                updated_at=stat.st_mtime,
            ))
        except OSError:
            continue

    results.sort(key=lambda m: m.updated_at, reverse=True)
    return results


def clear_session(session_id: str, cwd: str | None = None) -> bool:
    """删除一个会话文件。

    Returns:
        bool: 是否成功删除
    """
    cwd = cwd or os.getcwd()
    file_path = _session_file_path(cwd, session_id)

    try:
        os.unlink(file_path)
        return True
    except OSError:
        return False


def fork_session(session_id: str, cwd: str | None = None) -> str | None:
    """复制一个会话，返回新会话 ID。

    Args:
        session_id: 源会话 ID
        cwd: 工作目录

    Returns:
        str | None: 新会话 ID，失败返回 None
    """
    events = load_session(session_id, cwd, from_last_boundary=False)
    if not events:
        return None

    new_id = create_session(cwd)
    for event in events:
        if event.type != "system":
            save_event(
                session_id=new_id,
                event_type=event.type,
                content=event.content,
                cwd=cwd,
                metadata=event.metadata,
            )

    return new_id


# ── 内部辅助 ──


def _append_event(event: SessionEvent) -> None:
    """追加单个事件到 JSONL 文件。"""
    file_path = _session_file_path(event.cwd, event.session_id)
    _ensure_dir(os.path.dirname(file_path))
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(_event_to_dict(event), ensure_ascii=False) + "\n")


def _read_all_events(file_path: str) -> list[SessionEvent]:
    """从 JSONL 文件读取所有事件。"""
    events: list[SessionEvent] = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    event = _event_from_dict(data)
                    if event:
                        events.append(event)
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return events


def _read_last_event_uuid(file_path: str) -> str | None:
    """读取 JSONL 文件中最后一个事件的 UUID。"""
    events = _read_all_events(file_path)
    return events[-1].uuid if events else None


def _extract_title(events: list[SessionEvent]) -> str | None:
    """从会话事件中提取标题（第一个 user 事件的内容）。"""
    for event in events:
        if event.type == "user" and event.content.strip():
            text = event.content.strip()
            return text[:MAX_TITLE_LENGTH] + ("..." if len(text) > MAX_TITLE_LENGTH else "")
    return None
