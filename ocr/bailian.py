"""阿里云百炼视觉 OCR — 通用表格识别。"""
from __future__ import annotations

import base64
import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Callable

import config as cfg

logger = logging.getLogger(__name__)

LogCallback = Callable[[str], None]


def _ocr_log_file() -> str:
    return os.path.join(cfg.LOGS_DIR, f"ocr_{datetime.now():%Y-%m-%d}.log")


def _emit(msg: str, log_cb: LogCallback | None = None) -> None:
    logger.info(msg)
    try:
        with open(_ocr_log_file(), "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%H:%M:%S}] {msg}\n")
    except Exception:
        pass
    if log_cb:
        log_cb(msg)


def _post_json(url: str, headers: dict, payload: dict, *, timeout_sec: int = 120) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    for hk, hv in headers.items():
        req.add_header(hk, hv)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec, context=ctx) as r:
            text = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise ValueError(f"HTTP {e.code}: {err_body[:400]}") from e
    except urllib.error.URLError as e:
        raise ValueError(f"网络错误: {e.reason}") from e
    return json.loads(text)


def _usage_summary(resp: dict) -> str:
    usage = resp.get("usage") or {}
    in_tok = usage.get("input_tokens") or usage.get("prompt_tokens", "?")
    out_tok = usage.get("output_tokens") or usage.get("completion_tokens", "?")
    finish = (resp.get("choices") or [{}])[0].get("finish_reason", "?")
    content = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
    chars = len(content) if content else 0
    return f"输入tokens={in_tok} 输出tokens={out_tok} finish={finish} 字数={chars}"


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}") + 1
        if s != -1 and e > s:
            try:
                return json.loads(text[s:e])
            except json.JSONDecodeError:
                pass
        logger.warning("JSON 解析失败: %s...", text[:200])
        return {"headers": [], "rows": []}


def _image_to_base64(image_path: str) -> tuple[str, str]:
    ext = image_path.lower().rsplit(".", 1)[-1]
    mime_map = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "bmp": "image/bmp",
        "webp": "image/webp",
        "tif": "image/tiff",
        "tiff": "image/tiff",
    }
    mime = mime_map.get(ext, "image/jpeg")
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode(), mime


def _normalize_table_data(data: dict) -> dict:
    if not isinstance(data, dict):
        data = {}
    headers = data.get("headers") or []
    rows = data.get("rows") or []
    if not isinstance(headers, list):
        headers = []
    if not isinstance(rows, list):
        rows = []
    headers = [str(h) for h in headers]
    norm_rows = []
    col_count = len(headers)
    for row in rows:
        if isinstance(row, dict):
            if headers:
                norm_rows.append([str(row.get(h, "")) for h in headers])
            else:
                norm_rows.append([str(v) for v in row.values()])
        elif isinstance(row, list):
            cells = [str(c) if c is not None else "" for c in row]
            if col_count and len(cells) < col_count:
                cells.extend([""] * (col_count - len(cells)))
            norm_rows.append(cells[:col_count] if col_count else cells)
    if not headers and norm_rows:
        max_cols = max(len(r) for r in norm_rows)
        headers = [f"列{i + 1}" for i in range(max_cols)]
        col_count = len(headers)
        norm_rows = [
            r + [""] * (col_count - len(r)) if len(r) < col_count else r[:col_count]
            for r in norm_rows
        ]
    return {"headers": headers, "rows": norm_rows}


class TableOCR:
    def __init__(
        self,
        runtime: dict | None = None,
        log_cb: LogCallback | None = None,
        image_label: str = "",
    ):
        self.runtime = runtime or cfg.get_runtime_config()
        self.log_cb = log_cb
        self.image_label = image_label or ""

    def _log(self, msg: str) -> None:
        prefix = f"[{self.image_label}] " if self.image_label else ""
        _emit(prefix + msg, self.log_cb)

    def recognize(self, image_path: str) -> dict:
        try:
            two_stage = self.runtime.get("ocr_two_stage", True)
            mode = "两阶段" if two_stage else "单阶段"
            self._log(f"开始 OCR 识别（{mode}）")
            if two_stage:
                return self._recognize_two_stage(image_path)
            return self._recognize_single(image_path)
        except Exception as e:
            self._log(f"OCR 失败: {e}")
            logger.exception("OCR 失败")
            return {
                "success": False,
                "data": {"headers": [], "rows": []},
                "raw_text": "",
                "error": str(e),
            }

    def _recognize_two_stage(self, image_path: str) -> dict:
        stage1 = cfg.get_stage1_prompt()
        b64, mime = _image_to_base64(image_path)
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime};base64,{b64}",
                            "min_pixels": 28 * 28 * 256,
                            "max_pixels": 28 * 28 * 1280,
                        },
                    },
                    {"type": "text", "text": stage1},
                ],
            }
        ]
        self._log("[Stage1-视觉转写] 正在调用视觉模型...")
        resp1 = self._call_vision_api(messages, json_mode=False, stage="Stage1-视觉转写")
        transcribed = resp1["choices"][0]["message"]["content"].strip()
        self._log(f"[Stage1-视觉转写] 转写完成，共 {len(transcribed)} 字")

        stage2 = cfg.get_stage2_prompt()
        user_text = f"{stage2}\n\n【输入】\n{transcribed}"
        self._log("[Stage2-表格提取] 正在调用文本模型...")
        resp2 = self._call_text_api(user_text, stage="Stage2-表格提取")
        raw = resp2["choices"][0]["message"]["content"]
        data = _normalize_table_data(_parse_json(raw))
        self._log(
            f"识别完成：{len(data.get('headers', []))} 列，{len(data.get('rows', []))} 行"
        )
        return {
            "success": True,
            "data": data,
            "raw_text": raw,
            "transcribe_text": transcribed,
        }

    def _recognize_single(self, image_path: str) -> dict:
        prompt = cfg.get_single_prompt()
        b64, mime = _image_to_base64(image_path)
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime};base64,{b64}",
                            "min_pixels": 28 * 28 * 256,
                            "max_pixels": 28 * 28 * 1280,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        self._log("[单阶段] 正在调用视觉模型...")
        resp = self._call_vision_api(messages, json_mode=True, stage="单阶段")
        raw = resp["choices"][0]["message"]["content"]
        data = _normalize_table_data(_parse_json(raw))
        self._log(
            f"识别完成：{len(data.get('headers', []))} 列，{len(data.get('rows', []))} 行"
        )
        return {"success": True, "data": data, "raw_text": raw}

    def _call_vision_api(
        self, messages: list, json_mode: bool = False, stage: str = "视觉"
    ) -> dict:
        url = self.runtime["vision_api_url"]
        key = self.runtime["vision_api_key"]
        model = self.runtime["vision_api_model"]
        if not url or not key:
            raise ValueError("视觉 API 未配置，请在系统设置中填写 API Key。")
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": self.runtime.get("ocr_max_tokens", cfg.OCR_MAX_TOKENS),
            "temperature": 0.1,
        }
        if "qwen3" in model.lower():
            payload["enable_thinking"] = bool(
                self.runtime.get("vision_enable_thinking", False)
            )
        if json_mode and "ocr" not in model.lower():
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        timeout = self.runtime.get("ocr_api_timeout", cfg.OCR_API_TIMEOUT)
        self._log(f"[{stage}] 模型={model} 请求中...")
        t0 = time.time()
        resp = _post_json(url, headers, payload, timeout_sec=timeout)
        elapsed = time.time() - t0
        self._log(f"[{stage}] 完成 耗时={elapsed:.1f}s {_usage_summary(resp)}")
        return resp

    def _call_text_api(self, user_text: str, stage: str = "文本") -> dict:
        url = self.runtime.get("text_structure_api_url") or self.runtime["vision_api_url"]
        key = self.runtime.get("text_structure_api_key") or self.runtime["vision_api_key"]
        model = self.runtime.get("text_structure_model") or cfg.TEXT_STRUCTURE_MODEL
        if not url or not key:
            raise ValueError("文本结构化 API 未配置。")
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": user_text}],
            "max_tokens": self.runtime.get("ocr_max_tokens", cfg.OCR_MAX_TOKENS),
            "temperature": 0.1,
        }
        if "ocr" not in model.lower():
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        timeout = self.runtime.get("ocr_api_timeout", cfg.OCR_API_TIMEOUT)
        self._log(f"[{stage}] 模型={model} 请求中...")
        t0 = time.time()
        resp = _post_json(url, headers, payload, timeout_sec=timeout)
        elapsed = time.time() - t0
        self._log(f"[{stage}] 完成 耗时={elapsed:.1f}s {_usage_summary(resp)}")
        return resp


def recognize_table(
    image_path: str,
    runtime: dict | None = None,
    log_cb: LogCallback | None = None,
) -> dict:
    label = os.path.basename(image_path)
    return TableOCR(runtime, log_cb=log_cb, image_label=label).recognize(image_path)
