"""数据版本业务规则：代际发布、兼容核对与换代事件都收在这里。

数据版本侧模块向采集API取数链路提供换代事件：换代只失效绑定该数据源的
缓存快照，其他数据源的快照保持可读，不做全量重建。
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any

from app.services.scrapeapi_runtime import EVENT_TABLE, RESPONSE_TABLE, CACHE_TABLE, runtime
from app.store import store

MODULE = "dataversion"
REQUIRED_FIELDS = ["版本编号", "数据源标识", "当前代际", "依赖版本", "部署环境", "数据库连接"]
STATUS_ORDER = ["草稿", "版本核对中", "已发布", "已退役"]
ACTION_RULES = {"提交版本核对": "版本核对中", "发布版本": "已发布", "退役版本": "已退役"}
SPECIAL_ACTIONS = ["核对兼容性", "触发换代"]
NEGATIVE_ACTIONS = ["退役版本"]

# 换代前兼容核对口径：依赖版本、部署环境、数据库连接三项都要过。
SUPPORTED_DEPS = ["crawler-sdk 2.3", "crawler-sdk 2.4", "crawler-sdk 2.5"]
SUPPORTED_ENVS = ["prod-east", "prod-west", "staging"]
SUPPORTED_DB_SCHEMES = ["mysql", "postgres", "mongodb"]


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def _next_no(rows: list[dict[str, Any]], field: str, prefix: str) -> str:
    return f"{prefix}-{max((int(row.get('id', 0)) for row in rows), default=0) + 1:04d}"


class DataversionService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("版本编号", "")) or keyword in str(row.get("数据源标识", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["兼容状态"] = "待核对"
        entry["清单条目数"] = "0"
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"数据版本 {entry_id} 不存在或已归档"
        if action in SPECIAL_ACTIONS:
            return getattr(self, f"_{'check_compat' if action == '核对兼容性' else 'bump_generation'}")(entry)
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于数据版本可执行范围"
        target = ACTION_RULES[action]
        if target == "已发布" and entry.get("兼容状态") != "兼容":
            return None, "兼容核对未通过：请先执行「核对兼容性」并确认依赖版本、部署环境、数据库连接均兼容"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"数据版本已{action}"

    # ---------------------------------------------------------- 特殊动作
    def _check_compat(self, entry: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """核对依赖版本、部署环境与数据库连接兼容，三者全过才算兼容。"""
        if entry.get("status") not in {"版本核对中", "已发布"}:
            return None, f"当前状态「{entry.get('status')}」不能核对兼容性，请先提交版本核对"
        problems: list[str] = []
        dep = str(entry.get("依赖版本") or "")
        if not any(dep.startswith(prefix) for prefix in SUPPORTED_DEPS):
            problems.append(f"依赖版本「{dep}」不在支持范围（{'、'.join(SUPPORTED_DEPS)}）")
        env = str(entry.get("部署环境") or "")
        if env not in SUPPORTED_ENVS:
            problems.append(f"部署环境「{env}」不在支持范围（{'、'.join(SUPPORTED_ENVS)}）")
        conn = str(entry.get("数据库连接") or "")
        scheme = re.match(r"^([a-zA-Z][a-zA-Z0-9+]*)://", conn)
        if not scheme or scheme.group(1) not in SUPPORTED_DB_SCHEMES:
            problems.append(f"数据库连接「{conn}」协议不受支持（{'、'.join(SUPPORTED_DB_SCHEMES)}）")
        if problems:
            entry["兼容状态"] = "不兼容"
            entry["abnormal"] = True
            return entry, "兼容核对未通过：" + "；".join(problems)
        entry["兼容状态"] = "兼容"
        entry["abnormal"] = False
        return entry, "兼容核对通过：依赖版本、部署环境、数据库连接均兼容"

    def _bump_generation(self, entry: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """触发换代：代际 +1，发换代事件，只失效绑定该数据源的缓存快照。"""
        if entry.get("status") != "已发布":
            return None, f"当前状态「{entry.get('status')}」不能触发换代，请先发布版本"
        if entry.get("兼容状态") != "兼容":
            return None, "兼容核对未通过，不能触发换代"
        now = time.time()
        old_generation = str(entry.get("当前代际") or "G0")
        match = re.match(r"^G(\d+)$", old_generation)
        new_generation = f"G{(int(match.group(1)) if match else 0) + 1}"
        binding = str(entry.get("数据源标识") or "")
        affected = runtime.invalidate_for_generation(binding, new_generation, now=now)
        entry["当前代际"] = new_generation
        entry["上次换代时间"] = _iso(now)
        events = store.rows(EVENT_TABLE)
        events.append({
            "id": max((int(row.get("id", 0)) for row in events), default=0) + 1,
            "事件编号": _next_no(events, "事件编号", "EVT"),
            "版本编号": entry.get("版本编号"),
            "数据源标识": binding,
            "旧代际": old_generation,
            "新代际": new_generation,
            "事件类型": "数据源换代",
            "影响缓存数": affected,
            "创建时间": _iso(now),
            "时间戳": now,
        })
        return entry, (
            f"数据源 {binding} 已换代：{old_generation} → {new_generation}，"
            f"失效受影响缓存 {affected} 份，其余数据快照保持可读"
        )

    # ---------------------------------------------------------- 清单与事件
    def manifest(self, entry_id: int) -> dict[str, Any] | None:
        """数据版本侧清单：该数据源保留的API响应结果与数据快照，随记录一起保留。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        binding = str(entry.get("数据源标识") or "")
        responses = [
            row for row in store.rows(RESPONSE_TABLE) if row["数据源绑定"] == binding
        ]
        responses.sort(key=lambda item: int(item.get("id", 0)), reverse=True)
        snapshots = [
            row for row in store.rows(CACHE_TABLE) if row["数据源绑定"] == binding
        ]
        snapshots.sort(key=lambda item: int(item.get("id", 0)), reverse=True)
        return {
            "版本编号": entry.get("版本编号"),
            "数据源标识": binding,
            "当前代际": entry.get("当前代际"),
            "清单条目数": len(responses),
            "响应记录": responses,
            "数据快照": snapshots,
        }

    def list_events(self) -> list[dict[str, Any]]:
        events = sorted(store.rows(EVENT_TABLE), key=lambda item: int(item.get("id", 0)), reverse=True)
        return events
