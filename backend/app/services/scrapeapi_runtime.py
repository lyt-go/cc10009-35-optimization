"""采集API取数链路运行时：缓存身份、数据版本、限流窗口、快照与响应记录。

顺着取数逻辑定位，一次请求的处理顺序固定为：

    请求进入 → 幂等短路 → 状态拦截（下线/未上线给出明确结果）
    → 限流窗口计数（命中缓存也计一次，同一幂等键不重复扣）
    → 读取数据版本侧当前代际 → 校验缓存键（路径+参数+绑定+代际）
    → 命中缓存或单飞回源 → 生成数据快照与API响应结果
    → 幂等写回（重复提交只保留一次，保留优先级高者）
    → 回写数据版本侧清单，并同步采集API业务面。

旧实现只按请求路径识别缓存，数据源换代后仍返回旧快照；现在缓存键里
带请求参数指纹、数据源绑定与数据代际，换代后旧身份自然失效。
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

from app.store import store

CACHE_TABLE = "scrapeapi_cache"
RESPONSE_TABLE = "scrapeapi_response"
WINDOW_TABLE = "scrapeapi_window"
EVENT_TABLE = "dataversion_event"
VERSION_TABLE = "dataversion"
API_TABLE = "scrapeapi"

DEFAULT_RATE_LIMIT = 30
DEFAULT_WINDOW_SECONDS = 60
DEFAULT_TTL_SECONDS = 300

# 保留优先级：冲突双版本与幂等去重都按它取舍，高 > 中 > 低。
PRIORITY_RANK = {"高": 3, "中": 2, "低": 1}
SOURCE_PRIORITY = {
    "回源取数": "高",
    "冲突-新身份": "高",
    "缓存命中": "中",
    "冲突-旧身份": "中",
    "限流拦截": "低",
    "已下线拦截": "低",
    "未上线拦截": "低",
}


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def _next_id(rows: list[dict[str, Any]]) -> int:
    return max((int(row.get("id", 0)) for row in rows), default=0) + 1


def _parse_rate_limit(text: Any) -> tuple[int, int]:
    """解析「速率限制」字段，支持 '60次/60秒'、'60/60'；解析失败给默认值。"""
    match = re.search(r"(\d+)\s*次?\s*/\s*(\d+)\s*秒?", str(text or ""))
    if not match:
        return DEFAULT_RATE_LIMIT, DEFAULT_WINDOW_SECONDS
    limit, window = int(match.group(1)), int(match.group(2))
    return (limit or DEFAULT_RATE_LIMIT), (window or DEFAULT_WINDOW_SECONDS)


def _parse_ttl(text: Any) -> int:
    """解析「缓存策略」字段，支持 'TTL 300秒'、'300秒'、'300'；失败给默认值。"""
    match = re.search(r"(\d+)\s*秒?", str(text or ""))
    if not match:
        return DEFAULT_TTL_SECONDS
    return int(match.group(1)) or DEFAULT_TTL_SECONDS


def params_fingerprint(params: dict[str, Any]) -> str:
    """请求参数归一化指纹：排序后序列化再取哈希，参数不同则缓存身份不同。"""
    normalized = json.dumps(params or {}, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]


def identity_key(path: str, fingerprint: str, binding: str) -> str:
    """缓存身份键（不含代际）：定位同一请求身份的历史快照。"""
    return f"{path}|{fingerprint}|{binding}"


def cache_key(path: str, fingerprint: str, binding: str, generation: str) -> str:
    """完整缓存键：请求路径 + 参数指纹 + 数据源绑定 + 数据代际。"""
    return f"{identity_key(path, fingerprint, binding)}|{generation}"


def current_generation(binding: str) -> tuple[str, dict[str, Any] | None]:
    """读取数据版本侧当前已发布代际；没有已发布版本时退回 G0。"""
    rows = [
        row for row in store.rows(VERSION_TABLE)
        if str(row.get("数据源标识")) == binding and row.get("status") == "已发布"
    ]
    if not rows:
        return "G0", None
    row = max(rows, key=lambda item: int(item.get("id", 0)))
    return str(row.get("当前代际") or "G0"), row


def last_generation_event(binding: str) -> dict[str, Any] | None:
    events = [row for row in store.rows(EVENT_TABLE) if str(row.get("数据源标识")) == binding]
    if not events:
        return None
    return max(events, key=lambda item: int(item.get("id", 0)))


def _render_payload(entry: dict[str, Any], params: dict[str, Any], generation: str, now: float) -> dict[str, Any]:
    """模拟实际数据源取数：内容随 API、参数与代际确定，换代后内容指纹必变。"""
    seed = json.dumps(
        {"api": entry.get("API编号"), "params": params, "generation": generation},
        sort_keys=True, ensure_ascii=False, default=str,
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    rows = [{"行号": index + 1, "内容指纹": digest[index * 6: index * 6 + 6]} for index in range(3)]
    return {
        "数据行": rows,
        "行数": len(rows),
        "内容指纹": digest[:12],
        "数据代际": generation,
        "取数时间": _iso(now),
    }


class ScrapeRuntime:
    """采集API取数链路：限流、缓存、快照、响应记录都收在这一处。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._origin_locks: dict[str, threading.Lock] = {}

    # ------------------------------------------------------------------ 主链路
    def execute(
        self,
        entry_id: int,
        *,
        params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        """执行一次采集API取数，返回可解释的处理结果。"""
        now = time.time() if now is None else now
        params = dict(params or {})
        entry = store.find(API_TABLE, entry_id)
        if entry is None:
            return {"ok": False, "message": f"API定义 {entry_id} 不存在或已归档", "record": None, "versions": []}

        api_code = str(entry.get("API编号"))
        idem = str(idempotency_key or "").strip() or f"auto-{api_code}-{int(now * 1000)}"

        # 幂等短路：同一幂等键的重复提交直接返回已保留结果，
        # 不再扣减额度、不再生成快照。
        existing = self._find_response(api_code, idem)
        if existing is not None:
            return {
                "ok": existing.get("结果") == "成功",
                "message": (
                    f"重复提交按幂等返回已保留结果（{existing['响应编号']}，"
                    f"命中来源={existing['命中来源']}，保留优先级={existing['保留优先级']}），"
                    "额度不重复扣减"
                ),
                "record": existing,
                "versions": existing.get("版本结果集") or [],
            }

        # 状态拦截：API下线后在途请求返回明确结果，不悬挂、不扣额度。
        status = str(entry.get("status"))
        if status == "已下线":
            record = self._record_response(
                entry=entry, params=params, idem=idem, now=now, source="已下线拦截",
                result="失败", charged=0, window=None, snapshot=None, generation="-",
                note="API已下线，在途请求终止并返回明确结果",
            )
            return {"ok": False, "message": "API已下线：在途请求返回明确终止结果，不扣减额度", "record": record, "versions": []}
        if status != "已上线":
            record = self._record_response(
                entry=entry, params=params, idem=idem, now=now, source="未上线拦截",
                result="失败", charged=0, window=None, snapshot=None, generation="-",
                note=f"API当前状态为「{status}」，未上线不执行取数",
            )
            return {"ok": False, "message": f"API当前状态为「{status}」，未上线不执行取数", "record": record, "versions": []}

        # 限流窗口：缓存命中也要过这一关，不能绕过限流。
        limit, window_seconds = _parse_rate_limit(entry.get("速率限制"))
        with self._lock:
            admission = self._admit(api_code, limit, window_seconds, idem, now)
        window = admission["window"]
        if not admission["admitted"]:
            record = self._record_response(
                entry=entry, params=params, idem=idem, now=now, source="限流拦截",
                result="失败", charged=0, window=window, snapshot=None, generation="-",
                note=f"窗口 {window['窗口编号']} 额度 {limit} 次已用尽",
            )
            return {
                "ok": False,
                "message": f"限流窗口 {window['窗口编号']} 额度已用尽（{limit}次/{window_seconds}秒），本次不扣减",
                "record": record,
                "versions": [],
            }
        charged = admission["charged"]

        # 数据版本：缓存身份必须带上数据源当前代际。
        binding = str(entry.get("数据源绑定") or "")
        generation, _version_row = current_generation(binding)
        path = str(entry.get("请求路径") or "")
        fingerprint = params_fingerprint(params)
        ikey = identity_key(path, fingerprint, binding)
        ckey = cache_key(path, fingerprint, binding, generation)
        ttl = _parse_ttl(entry.get("缓存策略"))

        snapshot = self._latest_snapshot(ikey)
        window_start = int(window["窗口起始"])
        event = last_generation_event(binding)

        # 情形一：缓存命中（同代际、有效、未过期）。
        if (
            snapshot is not None
            and snapshot["数据代际"] == generation
            and snapshot["状态"] == "有效"
            and float(snapshot["过期时间戳"]) > now
        ):
            with self._lock:
                snapshot["命中次数"] = int(snapshot.get("命中次数", 0)) + 1
            record = self._record_response(
                entry=entry, params=params, idem=idem, now=now, source="缓存命中",
                result="成功", charged=charged, window=window, snapshot=snapshot,
                generation=generation, note=f"命中缓存快照 {snapshot['快照编号']}，未回源",
            )
            return {
                "ok": True,
                "message": f"缓存命中：返回快照 {snapshot['快照编号']}（代际 {generation}），本次扣减额度 {charged}",
                "record": record,
                "versions": [self._version_view("当前", snapshot)],
            }

        # 情形二：缓存过期与数据源换代在同一窗口发生 → 新旧身份冲突，保留两份版本结果。
        conflict = (
            snapshot is not None
            and snapshot["数据代际"] != generation
            and window_start <= float(snapshot["过期时间戳"]) <= now
            and event is not None
            and window_start <= float(event["时间戳"]) <= now
        )
        if conflict:
            old_version = self._version_view("冲突-旧身份", snapshot)
            new_snapshot, _created = self._fetch_origin(entry, params, generation, ckey, ikey, fingerprint, ttl, now)
            with self._lock:
                if snapshot["状态"] == "有效":
                    snapshot["状态"] = "已失效"
                    snapshot["保留优先级"] = "低"
            self._record_response(
                entry=entry, params=params, idem=f"{idem}#old", now=now, source="冲突-旧身份",
                result="成功", charged=0, window=window, snapshot=snapshot, generation=str(snapshot["数据代际"]),
                note="缓存过期与数据源换代同窗口：旧身份版本结果保留，不重复扣减额度",
                version_tag="冲突-旧身份",
            )
            record = self._record_response(
                entry=entry, params=params, idem=idem, now=now, source="冲突-新身份",
                result="成功", charged=charged, window=window, snapshot=new_snapshot, generation=generation,
                note="缓存过期与数据源换代同窗口：新身份回源取数",
                version_tag="冲突-新身份",
                versions=[old_version, self._version_view("冲突-新身份", new_snapshot)],
            )
            return {
                "ok": True,
                "message": (
                    f"缓存过期与数据源换代同窗口（窗口 {window['窗口编号']}）："
                    f"保留旧身份 {snapshot['快照编号']}（代际 {snapshot['数据代际']}）与"
                    f"新身份 {new_snapshot['快照编号']}（代际 {generation}）两份版本结果"
                ),
                "record": record,
                "versions": [old_version, self._version_view("冲突-新身份", new_snapshot)],
            }

        # 情形三：回源取数（无快照 / 快照过期 / 换代后旧身份失效）。
        if snapshot is None:
            reason = "无可用快照，首次回源"
        elif snapshot["数据代际"] != generation:
            reason = f"数据源换代（{snapshot['数据代际']} → {generation}），旧快照失效"
        else:
            reason = "快照已过期，回源刷新"
        new_snapshot, created = self._fetch_origin(entry, params, generation, ckey, ikey, fingerprint, ttl, now)
        if created and snapshot is not None and snapshot["数据代际"] != generation and snapshot["状态"] == "有效":
            with self._lock:
                snapshot["状态"] = "已失效"
                snapshot["保留优先级"] = "低"
        record = self._record_response(
            entry=entry, params=params, idem=idem, now=now, source="回源取数",
            result="成功", charged=charged, window=window, snapshot=new_snapshot,
            generation=generation, note=reason,
        )
        return {
            "ok": True,
            "message": f"回源取数：{reason}，生成快照 {new_snapshot['快照编号']}（代际 {generation}），本次扣减额度 {charged}",
            "record": record,
            "versions": [self._version_view("当前", new_snapshot)],
        }

    # ------------------------------------------------------------------ 限流窗口
    def _admit(self, api_code: str, limit: int, window_seconds: int, idem: str, now: float) -> dict[str, Any]:
        """固定窗口计数：请求按到达时刻落入唯一窗口，窗口切换不在边界重复计数。

        同一幂等键在同一窗口只扣一次；缓存命中同样走这里扣减。
        """
        start = int(now // window_seconds) * window_seconds
        rows = store.rows(WINDOW_TABLE)
        window = next(
            (row for row in rows if row["API编号"] == api_code and int(row["窗口起始"]) == start),
            None,
        )
        if window is None:
            window = {
                "id": _next_id(rows),
                "窗口编号": f"WIN-{api_code}-{start}",
                "API编号": api_code,
                "窗口起始": start,
                "窗口起始时间": _iso(start),
                "窗口时长秒": window_seconds,
                "额度上限": limit,
                "已用额度": 0,
                "扣减幂等键": [],
            }
            rows.append(window)
        window["额度上限"] = limit
        window["窗口时长秒"] = window_seconds
        if idem in window["扣减幂等键"]:
            return {"admitted": True, "charged": 0, "window": window}
        if int(window["已用额度"]) >= limit:
            return {"admitted": False, "charged": 0, "window": window}
        window["已用额度"] = int(window["已用额度"]) + 1
        window["扣减幂等键"].append(idem)
        return {"admitted": True, "charged": 1, "window": window}

    # ------------------------------------------------------------------ 缓存与回源
    def _latest_snapshot(self, ikey: str) -> dict[str, Any] | None:
        rows = [row for row in store.rows(CACHE_TABLE) if row["身份键"] == ikey]
        if not rows:
            return None
        return max(rows, key=lambda item: int(item.get("id", 0)))

    def _fetch_origin(
        self,
        entry: dict[str, Any],
        params: dict[str, Any],
        generation: str,
        ckey: str,
        ikey: str,
        fingerprint: str,
        ttl: int,
        now: float,
    ) -> tuple[dict[str, Any], bool]:
        """单飞回源：同一缓存键并发回源只留一个快照，其余请求复用先到的快照。"""
        lock = self._origin_locks.setdefault(ckey, threading.Lock())
        with lock:
            rows = store.rows(CACHE_TABLE)
            for row in rows:
                if row["缓存键"] == ckey and row["状态"] == "有效":
                    return row, False
            snapshot = {
                "id": _next_id(rows),
                "快照编号": f"SNAP-{_next_id(rows):04d}",
                "缓存键": ckey,
                "身份键": ikey,
                "API编号": entry.get("API编号"),
                "请求路径": entry.get("请求路径"),
                "参数指纹": fingerprint,
                "数据源绑定": entry.get("数据源绑定"),
                "数据代际": generation,
                "状态": "有效",
                "保留优先级": "高",
                "命中次数": 0,
                "内容": _render_payload(entry, params, generation, now),
                "创建时间": _iso(now),
                "时间戳": now,
                "过期时间": _iso(now + ttl),
                "过期时间戳": now + ttl,
            }
            rows.append(snapshot)
            return snapshot, True

    def invalidate_for_generation(self, binding: str, new_generation: str, now: float | None = None) -> int:
        """数据版本侧换代事件处理：只失效绑定该数据源的缓存，其他快照保持可读。"""
        now = time.time() if now is None else now
        affected = 0
        with self._lock:
            for row in store.rows(CACHE_TABLE):
                if (
                    row["数据源绑定"] == binding
                    and row["状态"] == "有效"
                    and row["数据代际"] != new_generation
                ):
                    row["状态"] = "已失效"
                    row["保留优先级"] = "低"
                    row["失效时间"] = _iso(now)
                    affected += 1
        return affected

    # ------------------------------------------------------------------ 响应记录
    def _find_response(self, api_code: str, idem: str) -> dict[str, Any] | None:
        for row in store.rows(RESPONSE_TABLE):
            if row["API编号"] == api_code and row["幂等键"] == idem:
                return row
        return None

    def _version_view(self, tag: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            "版本结果": tag,
            "快照编号": snapshot["快照编号"],
            "数据代际": snapshot["数据代际"],
            "内容": snapshot["内容"],
        }

    def _record_response(
        self,
        *,
        entry: dict[str, Any],
        params: dict[str, Any],
        idem: str,
        now: float,
        source: str,
        result: str,
        charged: int,
        window: dict[str, Any] | None,
        snapshot: dict[str, Any] | None,
        generation: str,
        note: str,
        version_tag: str = "当前",
        versions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """写响应记录：同一幂等键只保留一次，冲突时保留优先级高者。

        写入后回写数据版本侧清单（清单条目数），并同步采集API业务面。
        """
        priority = SOURCE_PRIORITY.get(source, "中")
        with self._lock:
            rows = store.rows(RESPONSE_TABLE)
            fingerprint = params_fingerprint(params)
            binding = str(entry.get("数据源绑定") or "")
            path = str(entry.get("请求路径") or "")
            for row in rows:
                if row["API编号"] == entry.get("API编号") and row["幂等键"] == idem:
                    if PRIORITY_RANK[priority] > PRIORITY_RANK[row["保留优先级"]]:
                        row.update(self._record_fields(
                            entry, path, binding, fingerprint, idem, now, source, result,
                            charged, window, snapshot, generation, note, version_tag,
                            versions, priority, record_id=row["id"], record_no=row["响应编号"],
                        ))
                        self._sync_after_record(row)
                    return row
            record_id = _next_id(rows)
            record = self._record_fields(
                entry, path, binding, fingerprint, idem, now, source, result,
                charged, window, snapshot, generation, note, version_tag,
                versions, priority, record_id=record_id, record_no=f"RESP-{record_id:04d}",
            )
            rows.append(record)
            self._sync_after_record(record)
            return record

    def _record_fields(
        self,
        entry: dict[str, Any],
        path: str,
        binding: str,
        fingerprint: str,
        idem: str,
        now: float,
        source: str,
        result: str,
        charged: int,
        window: dict[str, Any] | None,
        snapshot: dict[str, Any] | None,
        generation: str,
        note: str,
        version_tag: str,
        versions: list[dict[str, Any]] | None,
        priority: str,
        *,
        record_id: int,
        record_no: str,
    ) -> dict[str, Any]:
        window_no = window["窗口编号"] if window else "-"
        remaining = (int(window["额度上限"]) - int(window["已用额度"])) if window else 0
        snapshot_no = snapshot["快照编号"] if snapshot else "-"
        scope = (
            f"API={entry.get('API编号')} 路径={path} 参数指纹={fingerprint} "
            f"数据源={binding} 代际={generation} 窗口={window_no} 快照={snapshot_no}"
        )
        return {
            "id": record_id,
            "响应编号": record_no,
            "API定义ID": entry.get("id"),
            "API编号": entry.get("API编号"),
            "请求路径": path,
            "参数指纹": fingerprint,
            "数据源绑定": binding,
            "数据代际": generation,
            "缓存键": snapshot["缓存键"] if snapshot else "-",
            "幂等键": idem,
            "命中来源": source,
            "结果": result,
            "版本结果": version_tag,
            "版本结果集": versions or [],
            "窗口编号": window_no,
            "窗口内序号": int(window["已用额度"]) if window else 0,
            "额度扣减": charged,
            "剩余额度": remaining,
            "快照编号": snapshot_no,
            "保留优先级": priority,
            "处理范围": scope,
            "说明": note,
            "结果内容": snapshot["内容"] if snapshot else None,
            "创建时间": _iso(now),
            "时间戳": now,
        }

    def _sync_after_record(self, record: dict[str, Any]) -> None:
        """回写数据版本侧清单，并同步更新采集API业务面。"""
        binding = record["数据源绑定"]
        count = sum(1 for row in store.rows(RESPONSE_TABLE) if row["数据源绑定"] == binding)
        for row in store.rows(VERSION_TABLE):
            if str(row.get("数据源标识")) == binding:
                row["清单条目数"] = str(count)
        entry = store.find(API_TABLE, int(record["API定义ID"]))
        if entry is not None:
            entry["最近命中来源"] = record["命中来源"]
            entry["最近响应编号"] = record["响应编号"]
            entry["累计响应数"] = str(int(entry.get("累计响应数") or 0) + 1)
            entry["最近响应时间"] = record["创建时间"]

    # ------------------------------------------------------------------ 查询
    def list_responses(
        self,
        *,
        api_code: str | None = None,
        source: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = sorted(store.rows(RESPONSE_TABLE), key=lambda item: int(item.get("id", 0)), reverse=True)
        if api_code:
            rows = [row for row in rows if row["API编号"] == api_code]
        if source:
            rows = [row for row in rows if row["命中来源"] == source]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def list_cache(
        self,
        *,
        api_code: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = sorted(store.rows(CACHE_TABLE), key=lambda item: int(item.get("id", 0)), reverse=True)
        if api_code:
            rows = [row for row in rows if row["API编号"] == api_code]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def list_windows(self, *, api_code: str | None = None) -> list[dict[str, Any]]:
        rows = sorted(store.rows(WINDOW_TABLE), key=lambda item: (item["API编号"], int(item["窗口起始"])))
        if api_code:
            rows = [row for row in rows if row["API编号"] == api_code]
        return rows


runtime = ScrapeRuntime()
