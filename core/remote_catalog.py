"""Fetch remote Skill / Expert catalogs from network (JSON manifest + cache)."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path

from core.settings_store import get_setting, set_setting

logger = logging.getLogger(__name__)

_CACHE_TTL_SEC = 3600
_USER_AGENT = "Buddy-RemoteCatalog/1.0"

# 官方远程目录（GitHub Raw）；可在 设置→系统 覆盖
DEFAULT_REMOTE_CATALOG_URL = (
    "https://raw.githubusercontent.com/zezeqq/-agent/main/config/catalog.json"
)


def _cache_path() -> Path:
    from utils.path_utils import data_dir
    return data_dir() / "remote_catalog_cache.json"


def _fetch_json(url: str, timeout: float = 20.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("远程目录必须是 JSON 对象（含 skills / experts 等字段）")
    return data


def get_catalog_url() -> str:
    stored = get_setting("remote_catalog_url", "").strip()
    return stored or DEFAULT_REMOTE_CATALOG_URL


def ensure_catalog_url_configured() -> None:
    """首次启动写入默认远程目录 URL（用户可在设置中修改）。"""
    if not get_setting("remote_catalog_url", "").strip():
        set_setting("remote_catalog_url", DEFAULT_REMOTE_CATALOG_URL, "string")


def set_catalog_url(url: str) -> None:
    set_setting("remote_catalog_url", url.strip(), "string")


def load_cached_catalog() -> dict | None:
    path = _cache_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def fetch_remote_catalog(*, force: bool = False) -> dict:
    """Return merged remote manifest; uses disk cache when fresh."""
    url = get_catalog_url()
    if not url:
        cached = load_cached_catalog()
        return cached or {"skills": [], "experts": [], "fetched_at": 0, "source_url": ""}

    if not force:
        cached = load_cached_catalog()
        if cached and cached.get("source_url") == url:
            age = time.time() - float(cached.get("fetched_at") or 0)
            if age < _CACHE_TTL_SEC:
                return cached

    try:
        data = _fetch_json(url)
        payload = {
            "version": data.get("version", 1),
            "updated_at": data.get("updated_at", ""),
            "skills": list(data.get("skills") or []),
            "experts": list(data.get("experts") or []),
            "fetched_at": time.time(),
            "source_url": url,
        }
        _cache_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        set_setting("remote_catalog_last_fetch", str(int(payload["fetched_at"])), "string")
        logger.info("Remote catalog fetched: %d skills, %d experts", len(payload["skills"]), len(payload["experts"]))
        return payload
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("Remote catalog fetch failed: %s", exc)
        cached = load_cached_catalog()
        if cached:
            cached["fetch_error"] = str(exc)
            return cached
        raise


def remote_skills_merged_with_local() -> list[dict]:
    """Local RECOMMENDED_SKILLS + remote skills (remote wins on same name)."""
    from core.skill_catalog import RECOMMENDED_SKILLS

    by_name: dict[str, dict] = {}
    for s in RECOMMENDED_SKILLS:
        by_name[s.get("name", "").lower()] = dict(s)

    try:
        remote = fetch_remote_catalog()
    except Exception:
        remote = load_cached_catalog() or {"skills": []}

    for rs in remote.get("skills") or []:
        if not isinstance(rs, dict) or not rs.get("name"):
            continue
        key = str(rs["name"]).lower().replace(" ", "_")
        entry = dict(rs)
        entry.setdefault("skill_type", "prompt")
        entry.setdefault("category", "远程")
        entry.setdefault("icon", "🌐")
        entry["remote"] = True
        by_name[key] = entry

    return list(by_name.values())


def remote_experts_merged_with_local(local_experts: list[dict]) -> list[dict]:
    """Local EXPERTS + remote experts list."""
    by_name: dict[str, dict] = {}
    for e in local_experts:
        by_name[e.get("name", "")] = dict(e)

    try:
        remote = fetch_remote_catalog()
    except Exception:
        remote = load_cached_catalog() or {"experts": []}

    for re in remote.get("experts") or []:
        if not isinstance(re, dict) or not re.get("name"):
            continue
        by_name[re["name"]] = {
            "name": re["name"],
            "provider": re.get("provider", "远程"),
            "desc": re.get("desc", re.get("description", "")),
            "tags": re.get("tags", []),
            "category": re.get("category", "远程"),
            "prompt": re.get("prompt", re.get("system_prompt", "")),
            "remote": True,
        }

    return list(by_name.values())
