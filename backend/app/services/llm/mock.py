"""Offline provider used when no API key is configured.

This exists so the whole chain — upload, SSE framing, partial-advice
extraction, JSON parsing, persistence, result card — can be exercised and
verified without a key or a network. It returns a fixed dish and *simulates*
token-by-token streaming, so the streaming path is genuinely exercised rather
than bypassed.

It is clearly labelled "mock" everywhere it surfaces, so sample data can never
be mistaken for a real analysis.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator

from app.services.llm.base import TokenUsage, VisionRequest

# Small per-chunk delay so the streaming UI has something to show.
CHUNK_SIZE = 14
CHUNK_DELAY_SECONDS = 0.02

_ADVICE_QUICK = (
    "番茄炒蛋的食材搭配本身比较均衡：鸡蛋提供优质蛋白，番茄提供维生素 C 和番茄红素。\n\n"
    "如果想让这一餐更完整，可以考虑配一份主食和一份深色蔬菜。"
)

_ADVICE_DETAILED = """\
这道菜的主要构成是鸡蛋和番茄，属于家常快手菜，有几个可以留意的地方：

- **蛋白质**：鸡蛋是这道菜里蛋白质的主要来源，整体搭配比较扎实。
- **脂肪**：家常做法的用油量往往比看上去多，而这一点从照片上完全判断不出来，
  也是这道菜热量弹性最大的来源。
- **糖**：不少做法会加糖来平衡番茄的酸味，如果加过，值得知道。
- **番茄红素**：它和油脂一起加热后吸收率更高，这道菜的烹调方式在这一点上是有利的。

如果想调整，可以考虑的方向：
- 想控制总热量：用不粘锅，把油减到 10 g 左右会容易做到得多。
- 想增加膳食纤维：搭配一份焯青菜或杂粮饭。
- 番茄本身含钾较高，需要控制钠摄入的人可以少放盐和酱油。
"""

_OVERALL_QUICK = {
    "summary": "以蛋白质和番茄为主，蔬菜量偏少，口味偏咸鲜。",
    "aspects": [
        {"label": "蛋白质", "level": "偏多", "note": "鸡蛋是这一餐蛋白质的主要来源。"},
        {"label": "蔬菜", "level": "偏少", "note": "只有番茄，没有绿叶菜。"},
        {"label": "烹调方式", "level": None, "note": "炒制，咸味主要来自酱油和盐。"},
    ],
}

_OVERALL_DETAILED = {
    "summary": "以蛋白质为主，配菜偏少，主食缺失，口味偏咸鲜。",
    "aspects": [
        {"label": "蛋白质", "level": "偏多", "note": "鸡蛋是主要来源，整体比例较高。"},
        {"label": "蔬菜", "level": "偏少", "note": "只有番茄，没有绿叶菜。"},
        {"label": "主食", "level": "偏少", "note": "照片里没有看到米饭、面食一类的主食。"},
        {"label": "烹调方式", "level": None, "note": "炒制，油脂用量从照片无法判断。"},
        {"label": "口味", "level": None, "note": "番茄的酸味搭配咸鲜，偏家常口味。"},
    ],
}


# Key order matches what the prompt asks the real model for, so demo mode
# streams the same way a real call does: `advice` arrives early, which is what
# makes the partial-advice streaming visible instead of dead air.
_PAYLOAD_QUICK = {
    "dish_name": "番茄炒蛋",
    "dish_name_alternatives": ["西红柿炒鸡蛋"],
    "confidence": 0.82,
    "confidence_reason": "照片中可见块状番茄与凝固的蛋块，颜色和形态都符合这道菜的典型特征。",
    "advice": _ADVICE_QUICK,
    "ingredients": [
        {"name": "鸡蛋", "estimated_amount": "约 2 个（约 100g）", "note": None},
        {"name": "番茄", "estimated_amount": "约 200g", "note": None},
        {"name": "食用油", "estimated_amount": "约 15g", "note": "用量由照片无法确认"},
    ],
    "portion_estimate": "约 300g，约 1 人份",
    "nutrition": {
        "calories_kcal": 285,
        "protein_g": 14.2,
        "fat_g": 20.5,
        "carbs_g": 9.6,
        "fiber_g": None,
        "sugar_g": None,
        "sodium_mg": None,
        "basis": "按图中约 300g 份量、家常做法（含约 15g 食用油）折算",
    },
    "overall": _OVERALL_QUICK,
    "additional_dishes": [],
    "risk_notes": ["含鸡蛋，对蛋类过敏的人需要留意。", "家常做法用盐和酱油，钠含量取决于调味量。"],
    "uncertainty_notes": [
        "照片无法反映实际用油量，热量估算的偏差主要来自这里。",
        "无法确认是否加糖。",
    ],
}

_PAYLOAD_DETAILED = {
    "dish_name": "番茄炒蛋",
    "dish_name_alternatives": ["西红柿炒鸡蛋", "番茄滑蛋"],
    "confidence": 0.78,
    "confidence_reason": "可辨认出番茄块与炒蛋的形态，但照片中缺少能确认具体做法的细节。",
    "advice": _ADVICE_DETAILED,
    "ingredients": [
        {"name": "鸡蛋", "estimated_amount": "约 2 个（约 100g）", "note": "呈凝固块状"},
        {"name": "番茄", "estimated_amount": "约 200g", "note": "切块，部分已软化出汁"},
        {"name": "食用油", "estimated_amount": "约 15–25g", "note": "用量无法从照片确认"},
        {"name": "食盐", "estimated_amount": "约 1–2g", "note": None},
        {"name": "白砂糖", "estimated_amount": "约 4g", "note": "家常做法常加，无法确认是否添加"},
        {"name": "小葱", "estimated_amount": "少量", "note": "若有撒葱花"},
    ],
    "portion_estimate": "约 300g，约 1 人份（按常见浅盘平铺一层估算）",
    "nutrition": {
        "calories_kcal": 285,
        "protein_g": 14.2,
        "fat_g": 20.5,
        "carbs_g": 9.6,
        "fiber_g": 1.8,
        "sugar_g": 6.4,
        "sodium_mg": 620,
        "basis": "按图中约 300g 份量、家常做法（含约 15g 食用油与约 1.5g 食盐）折算",
    },
    "overall": _OVERALL_DETAILED,
    "additional_dishes": [],
    "risk_notes": [
        "含鸡蛋，对蛋类过敏的人需要留意。",
        "番茄与鸡蛋都属于常见致敏原范畴，但多数人可正常食用。",
        "家常做法用盐和酱油，成品钠含量取决于调味量。",
    ],
    "uncertainty_notes": [
        "用油量无法从照片判断，这是热量估算中最大的不确定来源。",
        "无法确认是否额外加了糖或酱油。",
        "配角的具体克重只能按常见份量推算。",
    ],
}


_ADDITIONAL_DISH = {
    "dish_name": "米饭",
    "confidence": 0.74,
    "confidence_reason": "另一张照片里可见一碗盛好的白米饭，形态明确。",
    "advice": "白米饭主要提供碳水化合物，和这道菜搭配着吃很常见。",
    "ingredients": [{"name": "大米", "estimated_amount": "约 150g（熟重）", "note": None}],
    "portion_estimate": "约 150g，约 1 小碗",
    "nutrition": {
        "calories_kcal": 174,
        "protein_g": 3.9,
        "fat_g": 0.5,
        "carbs_g": 38.6,
        "fiber_g": 0.5,
        "sugar_g": 0.1,
        "sodium_mg": 2,
        "basis": "按图中约 150g 熟米饭折算",
    },
    "risk_notes": [],
    "uncertainty_notes": ["份量按常见小碗估算。"],
}


def _chat_reply_sample() -> str:
    """Sample for a conversation follow-up: prose, not JSON.

    A chat turn has no images to re-examine, so the mock answers from the
    already-extracted result, exactly as the real prompt instructs.
    """
    return (
        "从上一轮提取的结果看，这道菜的热量主要来自烹调用油，而不是食材本身"
        "——鸡蛋和番茄都是热量不高的食材。\n\n"
        "如果你想让它更清淡一些，可以考虑：\n\n"
        "- 用不粘锅，把油量减到 10 g 左右\n"
        "- 番茄先下锅炒出汁，再回锅和蛋一起翻匀，这样少油也不影响口感\n\n"
        "另外提醒一句：我这边看不到你之前上传的照片，以上都是基于上一轮提取出的"
        "结果在说。如果你希望我重新看照片确认某个细节，可以再发一张。"
    )


class MockProvider:
    """Deterministic offline provider. Never contacts the network."""

    name = "mock"

    def _render(self, request: VisionRequest) -> str:
        if not request.images:
            return _chat_reply_sample()

        base = _PAYLOAD_DETAILED if request.mode == "detailed" else _PAYLOAD_QUICK
        # Shallow copy: we only ever replace whole values below, never mutate
        # the module-level literals.
        payload = {**base}

        if len(request.images) > 1:
            payload["additional_dishes"] = [dict(_ADDITIONAL_DISH)]
            payload["uncertainty_notes"] = [
                *base["uncertainty_notes"],
                f"本次综合了 {len(request.images)} 张照片的信息。",
            ]

        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _record_usage(request: VisionRequest, text: str) -> None:
        """Fill in plausible token counts.

        The timings are real (they come from the sleeps below), but the token
        counts are estimated from output length — no tokenizer is involved, and
        thinking is always off here. Good enough to exercise the diagnostic
        logging, and clearly labelled ``mock`` in the result either way.
        """
        estimated = max(1, len(text) // 2)
        request.metrics.usage = TokenUsage(
            prompt_tokens=None,
            completion_tokens=estimated,
            total_tokens=estimated,
        )
        request.metrics.reasoning_chars = 0

    async def analyze(self, request: VisionRequest) -> str:
        # A touch of latency so the UI's loading state is visible in demo mode.
        await asyncio.sleep(0.4)
        text = self._render(request)
        request.metrics.request_ms = 400
        self._record_usage(request, text)
        return text

    async def astream(self, request: VisionRequest) -> AsyncIterator[str]:
        text = self._render(request)
        await asyncio.sleep(0.2)
        request.metrics.request_ms = 200

        started = time.perf_counter()
        first_at: float | None = None
        for start in range(0, len(text), CHUNK_SIZE):
            if first_at is None:
                first_at = time.perf_counter()
                request.metrics.first_token_ms = int(
                    (first_at - started) * 1000
                ) + request.metrics.request_ms
            yield text[start : start + CHUNK_SIZE]
            await asyncio.sleep(CHUNK_DELAY_SECONDS)

        if first_at is not None:
            request.metrics.generation_ms = int((time.perf_counter() - first_at) * 1000)
        self._record_usage(request, text)
