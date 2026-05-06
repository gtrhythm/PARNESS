from typing import Dict, List
from .models import PaperEditorInput, PaperEditorOutput, EditSuggestion

class PaperEditor:
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def edit(self, input_data: PaperEditorInput) -> PaperEditorOutput:
        draft = input_data.paper_draft
        reviews = input_data.review_comments
        
        draft_text = self._format_draft(draft)
        reviews_text = self._format_reviews(reviews)
        
        prompt = f"""作为论文编辑，根据审稿意见修改论文：

原始论文：
{draft_text}

审稿意见：
{reviews_text}

请对论文进行润色和修改，包括：
1. 语言润色
2. 清晰度提升
3. 结构优化
4. 格式规范

返回JSON格式：
{{
  "revised_sections": {{
    "abstract": "修改后的摘要",
    "introduction": "修改后的引言",
    "method": "修改后的方法",
    "experiment": "修改后的实验",
    "conclusion": "修改后的结论"
  }},
  "edits_made": [
    {{
      "section": "abstract",
      "original": "...",
      "suggested": "...",
      "reason": "..."
    }}
  ],
  "summary": "修改总结"
}}
"""
        
        response = await self.llm.chat(prompt)
        revised_draft, edits = self._parse_response(response, draft)
        
        return PaperEditorOutput(
            revised_draft=revised_draft,
            edits_made=edits,
            summary=f"完成了 {len(edits)} 处修改"
        )
    
    def _format_draft(self, draft: Dict) -> str:
        lines = []
        for key in ["title", "abstract", "introduction", "method", "experiment", "conclusion"]:
            if key in draft:
                lines.append(f"=== {key.upper()} ===\n{draft[key]}\n")
        return "\n".join(lines)
    
    def _format_reviews(self, reviews: List[Dict]) -> str:
        lines = []
        for i, r in enumerate(reviews, 1):
            lines.append(f"{i}. [{r.get('severity', 'minor')}] {r.get('comment', '')}")
        return "\n".join(lines)
    
    def _parse_response(self, response: str, original: Dict) -> tuple:
        import json
        
        try:
            data = json.loads(response)
            revised = {**original, **data.get("revised_sections", {})}
            
            edits = []
            for item in data.get("edits_made", []):
                edits.append(EditSuggestion(
                    section=item.get("section", ""),
                    original_text=item.get("original", ""),
                    suggested_text=item.get("suggested", ""),
                    reason=item.get("reason", "")
                ))
            
            return revised, edits
        except json.JSONDecodeError:
            return original, []