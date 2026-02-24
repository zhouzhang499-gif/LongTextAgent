"""
短剧/漫剧 爆款检验器 (Drama Evaluator)
基于 LLM-as-a-Judge 与 Rejection Sampling 机制，对生成的爽文片段进行强阈值打分。
"""

import os
import yaml
import json
import re
from typing import Dict, Any, Tuple
from utils.llm_client import LLMClient


class RejectionException(Exception):
    """当生成内容未达到硬性分数标准时抛出的异常"""
    def __init__(self, score: float, suggestions: str, directive: str):
        self.score = score
        self.suggestions = suggestions
        self.directive = directive
        super().__init__(f"质量未达标 (分数: {score})。需重写。")


class DramaEvaluator:
    def __init__(self, llm: LLMClient, rubric_path: str = "examples/drama_rubric.yaml"):
        self.llm = llm
        self.rubric = self._load_rubric(rubric_path)
        self.target_score = self.rubric.get('target_pass_score', 90)

    def _load_rubric(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"找不到指定的裁判量规文件: {path}")
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def evaluate_section(self, content: str) -> Tuple[bool, float, str, str]:
        """
        评估生成的片段。
        
        Returns:
            passed (bool): 是否大于等于目标分数
            score (float): 总得分
            feedback (str): 提供给普通用户的详细反馈 (可打印)
            rewrite_directive (str): 提供给 Writer LLM 用于下一次重写的具体指令
        """
        # 构建评估 Prompt
        prompt = self._build_evaluation_prompt(content)
        
        # 调用 LLM 进行 JSON 评估
        response = self.llm.generate(prompt, max_tokens=1024)
        
        # 解析 JSON
        eval_data = self._parse_json_response(response)
        
        if not eval_data or "score" not in eval_data:
            return False, 0.0, "无法解析裁判返回的评估数据，强制打回重写。", "请注意遵循基本的小说写作规范，格式不要出问题。"

        # 获取分数
        total_score = float(eval_data.get('score', 0))
        
        # 组装给用户的反馈记录
        feedback_lines = []
        feedback_lines.append(f"【裁判总分】: {total_score} / 100")
        
        dim_scores = eval_data.get('dimension_scores', {})
        if dim_scores:
            feedback_lines.append(f"- 视觉转化率: {dim_scores.get('visual', 0)}")
            feedback_lines.append(f"- 情绪爽感: {dim_scores.get('emotion', 0)}")
            feedback_lines.append(f"- 钩子密度: {dim_scores.get('hook', 0)}")
            
        critique = eval_data.get('critique', '')
        if critique:
            feedback_lines.append(f"\n【裁判毒舌】: {critique}")
            
        directive = eval_data.get('revision_plan', '')
        if directive:
            feedback_lines.append(f"【重写建议】: {directive}")
                
        feedback_text = "\n".join(feedback_lines)
        
        # 判定是否通过
        passed = (total_score >= self.target_score)
        
        return passed, total_score, feedback_text, directive

    def _build_evaluation_prompt(self, content: str) -> str:
        """根据 yaml 配置动态构建 prompt"""
        criteria_text = ""
        for c in self.rubric.get('criteria', []):
            criteria_text += f"\n- {c['name']} (权重: {c['weight']})\n  描述: {c['description']}\n"
            for score_range, desc in c.get('levels', {}).items():
                criteria_text += f"    * {score_range}分: {desc}\n"
        
        instructions = self.rubric.get('judge_instructions', '')
        
        # 将原始文本中可能干扰 JSON 提取的大括号做个转义，或者让大模型忽略它
        prompt = f"""{instructions}
        
=== 评判标准 (Rubrics) ==={criteria_text}

=== 需要评估的草稿 ===
下面是由 AI 编剧生成的短剧剧本/极具画面感的小说片段：

{content}

请严格输出上方规定的 JSON 格式，不要包含其他解释性文字。
"""
        return prompt

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """尝试从大模型结果中提取并解析 JSON"""
        try:
            # 尝试直接解析
            return json.loads(response)
        except json.JSONDecodeError:
            # 使用正则提取 JSON block
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass
            
            # 再暴力找大括号
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
        return {}
