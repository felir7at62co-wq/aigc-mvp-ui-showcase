"""
AIGC Pipeline — 资产选择器

在资产生成前，使用 LLM 分析已提取的资产描述列表，
决定哪些资产值得生成、哪些可以跳过。
"""
import json
import re
import logging
from typing import Dict, Any, List

from core.llm_client import LLMClient

logger = logging.getLogger(__name__)


class AssetSelector:
    """
    生成前资产智能选择器。

    根据资产在剧本中的出场频率、重要性等维度，
    由 LLM 决定哪些资产应优先生成。
    """

    def __init__(
        self,
        llm_client: LLMClient,
        selector_template_path: str = "",
    ):
        self.llm_client = llm_client
        self.selector_template_path = selector_template_path

    def select(
        self,
        descriptions: List[Dict[str, str]],
        category: str = "character",
        max_select: int = 10,
    ) -> Dict[str, Any]:
        """
        分析资产描述列表，返回建议生成的资产子集。

        参数:
            descriptions: [{"name": str, "prompt": str, "episodes": str}, ...]
            category: "character" / "scene" / "prop"
            max_select: 建议生成的上限

        返回:
            {"selected": [name1, name2, ...], "skipped": [name3, ...],
             "reason": str, "success": bool}
        """
        if not descriptions:
            return {
                "selected": [],
                "skipped": [],
                "reason": "无资产描述",
                "success": True,
            }

        if len(descriptions) <= max_select:
            all_names = [d["name"] for d in descriptions]
            logger.info(
                f"资产数量({len(descriptions)})未超过上限({max_select})，全部选择"
            )
            return {
                "selected": all_names,
                "skipped": [],
                "reason": f"共{len(descriptions)}个，未超过上限{max_select}个",
                "success": True,
            }

        desc_lines = []
        for i, d in enumerate(descriptions, 1):
            episodes = d.get("episodes", "")
            name = d["name"]
            prompt_preview = d["prompt"][:60]
            ep_info = f" [集数: {episodes}]" if episodes else ""
            desc_lines.append(f"{i}. {name}{ep_info} — {prompt_preview}...")

        desc_text = "\n".join(desc_lines)

        prompt_text = (
            f"以下是已从剧本中提取的{category}资产描述列表。"
            f"请分析并决定哪些应该生成：\n\n"
            f"{desc_text}\n\n"
            f"分类：{category}\n"
            f"总数：{len(descriptions)}个\n"
            f"建议生成上限：{max_select}个\n\n"
            f"输出JSON格式：\n"
            f'{{"selected": ["资产名1", "资产名2", ...], '
            f'"skipped": ["资产名3", ...], '
            f'"reason": "简要说明选择理由"}}'
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "你是一位专业的影视制作统筹。你的任务是分析资产描述列表，"
                    "决定哪些资产值得生成。判断标准："
                    "1) 出场频率（集数越多越优先）"
                    "2) 对剧情的重要性（核心角色/道具优先）"
                    "3) 同类资产过多时只选最重要的前N个。"
                    "只输出一行JSON，不要其他文字。"
                ),
            },
            {"role": "user", "content": prompt_text},
        ]

        try:
            response = self.llm_client.generate(
                messages=messages,
                max_tokens=1024,
                temperature=0.3,
            )
            result = self._parse_response(response)
            logger.info(
                f"资产选择完成: {len(result.get('selected', []))}个选中, "
                f"{len(result.get('skipped', []))}个跳过"
            )
            return result
        except Exception as e:
            logger.error(f"资产选择失败: {e}")
            all_names = [d["name"] for d in descriptions]
            return {
                "selected": all_names,
                "skipped": [],
                "reason": f"LLM分析失败，全部选择: {e}",
                "success": False,
            }

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """解析 LLM 返回的 JSON"""
        response = response.strip()

        json_match = re.search(
            r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL
        )
        if json_match:
            response = json_match.group(1)

        start = response.find("{")
        end = response.rfind("}")
        if start >= 0 and end > start:
            response = response[start : end + 1]

        data = json.loads(response)
        return {
            "selected": data.get("selected", []),
            "skipped": data.get("skipped", []),
            "reason": data.get("reason", ""),
            "success": True,
        }
