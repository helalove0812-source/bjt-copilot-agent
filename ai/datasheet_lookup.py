from __future__ import annotations

from dataclasses import asdict, dataclass
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Iterable

from ai.llm_client import LLMUnavailable, chat_text
from ai.transistor_db import TransistorProfile, normalize_model_name


@dataclass(frozen=True)
class DatasheetSearchResult:
    title: str
    url: str
    snippet: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class DatasheetLookupResult:
    ok: bool
    model: str
    query: str
    profile: TransistorProfile | None = None
    sources: list[DatasheetSearchResult] | None = None
    confidence: str = "none"
    used_llm_api: bool = False
    llm_provider: str = ""
    llm_usage: dict | None = None
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "model": self.model,
            "query": self.query,
            "profile": asdict(self.profile) if self.profile else None,
            "sources": [source.to_dict() for source in (self.sources or [])],
            "confidence": self.confidence,
            "used_llm_api": self.used_llm_api,
            "llm_provider": self.llm_provider,
            "llm_usage": self.llm_usage or {},
            "error": self.error,
        }


SearchFn = Callable[[str, int], list[DatasheetSearchResult]]


def datasheet_lookup_enabled() -> bool:
    return str(os.getenv("BJT_DATASHEET_LOOKUP", "1")).strip().lower() not in {"0", "false", "no", "off"}


def lookup_datasheet_profile(
    model: str,
    *,
    limit: int = 5,
    search_fn: SearchFn | None = None,
) -> DatasheetLookupResult:
    clean_model = normalize_model_name(model)
    query = f"{clean_model} transistor datasheet VCEO IC Ptot hFE pinout"
    if not clean_model or clean_model == "UNKNOWN":
        return DatasheetLookupResult(ok=False, model=model, query=query, error="model is required")
    if not datasheet_lookup_enabled():
        return DatasheetLookupResult(ok=False, model=clean_model, query=query, error="datasheet lookup disabled")

    try:
        results = (search_fn or web_search_datasheet)(query, limit)
    except Exception as exc:
        return DatasheetLookupResult(ok=False, model=clean_model, query=query, error=str(exc) or exc.__class__.__name__)

    if not results:
        return DatasheetLookupResult(ok=False, model=clean_model, query=query, sources=[], error="no search results")

    try:
        profile, confidence, provider, usage = _extract_profile_with_llm(clean_model, results)
        return DatasheetLookupResult(
            ok=True,
            model=clean_model,
            query=query,
            profile=profile,
            sources=results,
            confidence=confidence,
            used_llm_api=True,
            llm_provider=provider,
            llm_usage=usage,
        )
    except (LLMUnavailable, ValueError, TypeError, json.JSONDecodeError):
        profile = _extract_profile_heuristically(clean_model, results)
        if profile is None:
            return DatasheetLookupResult(
                ok=False,
                model=clean_model,
                query=query,
                sources=results,
                error="could not extract required BJT ratings from search results",
            )
        return DatasheetLookupResult(
            ok=True,
            model=clean_model,
            query=query,
            profile=profile,
            sources=results,
            confidence="low",
            used_llm_api=False,
        )


def web_search_datasheet(query: str, limit: int = 5) -> list[DatasheetSearchResult]:
    backend = os.getenv("BJT_DATASHEET_SEARCH_BACKEND", "auto").strip().lower()
    if backend == "disabled":
        return []
    if backend in {"tavily", "auto"} and os.getenv("TAVILY_API_KEY"):
        return _search_tavily(query, limit)
    return _search_duckduckgo(query, limit)


def _search_tavily(query: str, limit: int) -> list[DatasheetSearchResult]:
    payload = {
        "api_key": os.environ["TAVILY_API_KEY"],
        "query": query,
        "search_depth": "basic",
        "max_results": max(1, min(int(limit), 8)),
        "include_answer": False,
    }
    request = urllib.request.Request(
        os.getenv("TAVILY_BASE_URL", "https://api.tavily.com").rstrip("/") + "/search",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    return [
        DatasheetSearchResult(
            title=str(item.get("title") or ""),
            url=str(item.get("url") or ""),
            snippet=str(item.get("content") or ""),
        )
        for item in data.get("results", [])[:limit]
    ]


def _search_duckduckgo(query: str, limit: int) -> list[DatasheetSearchResult]:
    url = "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    request = urllib.request.Request(url, headers={"User-Agent": "BJTagent/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            page = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"datasheet search failed: {exc}") from exc
    return _parse_duckduckgo_html(page, limit)


def _parse_duckduckgo_html(page: str, limit: int) -> list[DatasheetSearchResult]:
    results: list[DatasheetSearchResult] = []
    blocks = re.findall(r'<div class="result(?: results_links_deep)?[^"]*".*?</div>\s*</div>', page, flags=re.S)
    if not blocks:
        blocks = re.split(r'<div class="result', page)[1:]
    for block in blocks:
        title_match = re.search(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, flags=re.S)
        if not title_match:
            continue
        raw_url = html.unescape(title_match.group(1))
        parsed = urllib.parse.urlparse(raw_url)
        params = urllib.parse.parse_qs(parsed.query)
        final_url = params.get("uddg", [raw_url])[0]
        title = _strip_html(title_match.group(2))
        snippet_match = re.search(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', block, flags=re.S)
        if not snippet_match:
            snippet_match = re.search(r'<div[^>]+class="result__snippet"[^>]*>(.*?)</div>', block, flags=re.S)
        snippet = _strip_html(snippet_match.group(1)) if snippet_match else ""
        results.append(DatasheetSearchResult(title=title, url=final_url, snippet=snippet))
        if len(results) >= limit:
            break
    return results


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_profile_with_llm(
    model: str,
    results: Iterable[DatasheetSearchResult],
) -> tuple[TransistorProfile, str, str, dict]:
    source_payload = [source.to_dict() for source in results]
    system_text = """你是电子元器件 datasheet 抽取器，只能根据给定搜索结果提取 BJT 型号资料。
只输出 JSON 对象，不要 Markdown。不要猜测；字段证据不足就填 null。
必须提取：model、bjt_type(NPN/PNP)、description、vceo_max_v、ic_max_a、p_tot_w、hfe_typical([min,max])、package、pinout_hint、confidence(high/medium/low)。"""
    user_text = json.dumps({"model": model, "sources": source_payload}, ensure_ascii=False, indent=2)
    result = chat_text(system_text=system_text, user_text=user_text, timeout_s=30)
    data = _parse_json_object(result.text)
    profile = _profile_from_extracted_mapping(model, data, confidence_prefix="datasheet")
    confidence = str(data.get("confidence") or "medium")
    return profile, confidence, f"{result.provider}:{result.model}", result.usage


def _extract_profile_heuristically(
    model: str,
    results: Iterable[DatasheetSearchResult],
) -> TransistorProfile | None:
    text = "\n".join(f"{item.title}\n{item.snippet}" for item in results)
    bjt_type = "NPN" if re.search(r"\bNPN\b", text, re.I) else "PNP" if re.search(r"\bPNP\b", text, re.I) else ""
    if not bjt_type:
        return None
    data = {
        "model": model,
        "bjt_type": bjt_type,
        "description": "联网 datasheet 搜索提取的 BJT 型号资料",
        "vceo_max_v": _first_rating(text, ("VCEO", "Vceo", "Collector-Emitter Voltage")),
        "ic_max_a": _first_current_rating(text),
        "p_tot_w": _first_power_rating(text),
        "hfe_typical": _first_hfe_range(text),
        "package": _first_package(text),
        "pinout_hint": "联网资料提示：不同厂商/封装可能存在引脚差异，硬件执行前必须核对原始 datasheet。",
    }
    try:
        return _profile_from_extracted_mapping(model, data, confidence_prefix="datasheet")
    except ValueError:
        return None


def _profile_from_extracted_mapping(model: str, data: dict, *, confidence_prefix: str) -> TransistorProfile:
    bjt_type = str(data.get("bjt_type") or "").upper()
    if bjt_type not in {"NPN", "PNP"}:
        raise ValueError("missing bjt_type")
    vceo = _positive_float(data.get("vceo_max_v"))
    ic = _positive_float(data.get("ic_max_a"))
    p_tot = _positive_float(data.get("p_tot_w"))
    if vceo is None or ic is None or p_tot is None:
        raise ValueError("missing rating fields")
    hfe = data.get("hfe_typical") or [0, 0]
    if not isinstance(hfe, (list, tuple)) or len(hfe) < 2:
        hfe = [0, 0]
    return TransistorProfile(
        model=str(data.get("model") or model).strip() or model,
        bjt_type=bjt_type,
        description=str(data.get("description") or "联网 datasheet 搜索提取的 BJT 型号资料"),
        vceo_max_v=float(vceo),
        ic_max_a=float(ic),
        p_tot_w=float(p_tot),
        hfe_typical=(int(float(hfe[0] or 0)), int(float(hfe[1] or 0))),
        package=str(data.get("package") or ""),
        pinout_hint=str(data.get("pinout_hint") or "硬件执行前必须核对原始 datasheet 和 E/B/C 引脚。"),
        confidence=f"{confidence_prefix}_lookup",
    )


def _parse_json_object(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("No JSON object")
    return json.loads(stripped[start : end + 1])


def _positive_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _first_rating(text: str, labels: tuple[str, ...]) -> float | None:
    for label in labels:
        match = re.search(label + r".{0,40}?(\d+(?:\.\d+)?)\s*V", text, re.I | re.S)
        if match:
            return float(match.group(1))
    return None


def _first_current_rating(text: str) -> float | None:
    match = re.search(r"(?:Ic|Collector Current).{0,50}?(\d+(?:\.\d+)?)\s*(mA|A)", text, re.I | re.S)
    if not match:
        return None
    value = float(match.group(1))
    return value / 1000.0 if match.group(2).lower() == "ma" else value


def _first_power_rating(text: str) -> float | None:
    match = re.search(r"(?:Ptot|Pd|Power Dissipation).{0,50}?(\d+(?:\.\d+)?)\s*(mW|W)", text, re.I | re.S)
    if not match:
        return None
    value = float(match.group(1))
    return value / 1000.0 if match.group(2).lower() == "mw" else value


def _first_hfe_range(text: str) -> list[int]:
    match = re.search(r"(?:hFE|DC Current Gain).{0,40}?(\d+)\s*(?:-|to|~|～)\s*(\d+)", text, re.I | re.S)
    if not match:
        return [0, 0]
    return [int(match.group(1)), int(match.group(2))]


def _first_package(text: str) -> str:
    packages = re.findall(r"\b(?:TO-92|SOT-23|TO-220|TO-18|SOT-89)\b", text, re.I)
    return " / ".join(dict.fromkeys(item.upper() for item in packages))
