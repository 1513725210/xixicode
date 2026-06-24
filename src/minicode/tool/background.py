"""Background Task Registry — 后台 Shell 任务管理。

参考 MiniCode background-tasks.ts 的设计：
- 前后台分离：同步工具 ≠ 后台持续任务
- 后台命令以 & 结尾时，detach 并注册为 task
- TUI 可单独展示后台任务状态

V1 实现：最小版本 — 仅注册/查询/取消，不进完整 task manager。
"""

import time
import uuid
from dataclasses import dataclass, field


@dataclass
class BackgroundTask:
    """后台任务记录。

    Attributes:
        task_id: 唯一任务 ID
        type: 任务类型（固定 local_bash）
        command: 执行的命令
        pid: 进程 ID
        status: running / completed / failed / cancelled
        started_at: 启动时间戳
        completed_at: 完成时间戳
        cwd: 工作目录
    """

    task_id: str
    type: str = "local_bash"
    command: str = ""
    pid: int = -1
    status: str = "running"
    started_at: float = 0.0
    completed_at: float | None = None
    cwd: str = ""


class BackgroundTaskRegistry:
    """后台任务注册表。

    V1: 简单内存注册表，进程结束后手动标记完成。
    V2: 可扩展为自动监控子进程退出状态。
    """

    def __init__(self):
        self._tasks: dict[str, BackgroundTask] = {}

    def register(
        self,
        command: str,
        pid: int,
        cwd: str = ".",
    ) -> BackgroundTask:
        """注册一个后台任务。

        Args:
            command: 执行的命令字符串
            pid: 进程 ID
            cwd: 工作目录

        Returns:
            BackgroundTask: 注册的任务记录
        """
        task_id = uuid.uuid4().hex[:8]
        task = BackgroundTask(
            task_id=task_id,
            command=command,
            pid=pid,
            cwd=cwd,
            started_at=time.time(),
        )
        self._tasks[task_id] = task
        return task

    def mark_completed(self, task_id: str, success: bool = True) -> BackgroundTask | None:
        """标记任务完成。

        Args:
            task_id: 任务 ID
            success: 是否成功

        Returns:
            BackgroundTask | None
        """
        task = self._tasks.get(task_id)
        if task:
            task.status = "completed" if success else "failed"
            task.completed_at = time.time()
        return task

    def mark_cancelled(self, task_id: str) -> BackgroundTask | None:
        """标记任务取消。"""
        task = self._tasks.get(task_id)
        if task:
            task.status = "cancelled"
            task.completed_at = time.time()
        return task

    def get(self, task_id: str) -> BackgroundTask | None:
        """获取任务。"""
        return self._tasks.get(task_id)

    def list_running(self) -> list[BackgroundTask]:
        """列出运行中的任务。"""
        return [t for t in self._tasks.values() if t.status == "running"]

    def list_all(self) -> list[BackgroundTask]:
        """列出所有任务（按启动时间倒序）。"""
        return sorted(self._tasks.values(), key=lambda t: t.started_at, reverse=True)

    def format_for_display(self) -> str:
        """格式化为 TUI 展示文本。"""
        tasks = self.list_all()
        if not tasks:
            return "（无后台任务）"

        lines = []
        for t in tasks:
            status_icon = {"running": "●", "completed": "✓", "failed": "✗", "cancelled": "○"}.get(t.status, "?")
            lines.append(f"  {status_icon} [{t.task_id}] {t.command[:60]}")
        return "\n".join(lines)

    @property
    def count(self) -> int:
        return len(self._tasks)

    @property
    def running_count(self) -> int:
        return len(self.list_running())


# ── 全局默认实例 ──

_default_registry: BackgroundTaskRegistry | None = None


def get_registry() -> BackgroundTaskRegistry:
    """获取全局后台任务注册表。"""
    global _default_registry
    if _default_registry is None:
        _default_registry = BackgroundTaskRegistry()
    return _default_registry
