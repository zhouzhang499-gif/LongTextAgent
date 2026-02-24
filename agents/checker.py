"""
一致性检查器
检查生成内容的逻辑一致性
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import os
import yaml
import json
import re

from utils.llm_client import LLMClient
from memory.settings_store import SettingsStore


class IssueType(Enum):
    """问题类型"""
    CHARACTER_NAME = "人物名称不一致"
    CHARACTER_TRAIT = "人物性格不一致"
    TIMELINE = "时间线矛盾"
    SETTING = "设定冲突"
    PLOT_HOLE = "情节漏洞"
    LOGIC = "逻辑问题"
    CONTINUITY = "连续性问题"


class IssueSeverity(Enum):
    """问题严重程度"""
    LOW = "低"
    MEDIUM = "中"
    HIGH = "高"
    CRITICAL = "严重"


@dataclass
class ConsistencyIssue:
    """一致性问题"""
    type: IssueType
    severity: IssueSeverity
    description: str
    location: str  # 问题位置描述
    suggestion: str  # 修改建议
    related_content: str = ""  # 相关内容片段
    original_text: str = ""    # 原文片段（用于修复）
    fixed_text: str = ""       # 修复后的文本（用于修复）
    auto_fixable: bool = False # 是否可自动修复


@dataclass
class CheckResult:
    """检查结果"""
    passed: bool
    issues: List[ConsistencyIssue]
    summary: str
    checked_items: int
    

class ConsistencyChecker:
    """
    一致性检查器
    
    检查项：
    1. 人物名称一致性
    2. 人物行为/性格一致性
    3. 时间线逻辑
    4. 设定冲突
    5. 未回收的伏笔提醒
    """
    
    def __init__(
        self,
        llm: LLMClient,
        settings_store: Optional[SettingsStore] = None
    ):
        self.llm = llm
        self.settings_store = settings_store
        
        # 加载外部提示词模板
        self.prompts = {}
        try:
            prompts_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "prompts.yaml")
            if os.path.exists(prompts_path):
                with open(prompts_path, 'r', encoding='utf-8') as f:
                    self.prompts = yaml.safe_load(f).get("checker", {})
        except Exception as e:
            print(f"[-] 警告：加载 checker 提示词模板失败 ({e})，将使用默认内置模板。") or SettingsStore()
    
    def check_content(
        self,
        content: str,
        chapter_id: int = 0,
        previous_content: str = ""
    ) -> CheckResult:
        """
        检查内容一致性
        
        Args:
            content: 待检查的内容
            chapter_id: 章节ID
            previous_content: 前文（用于连续性检查）
        
        Returns:
            检查结果
        """
        issues = []
        checked_items = 0
        
        # 1. 检查人物名称
        name_issues = self._check_character_names(content)
        issues.extend(name_issues)
        checked_items += 1
        
        # 2. 检查人物行为一致性
        if self.settings_store.characters:
            behavior_issues = self._check_character_behavior(content)
            issues.extend(behavior_issues)
            checked_items += 1
        
        # 3. 检查连续性（如果有前文）
        if previous_content:
            continuity_issues = self._check_continuity(content, previous_content)
            issues.extend(continuity_issues)
            checked_items += 1
        
        # 4. 检查设定冲突
        if self.settings_store.world_settings:
            setting_issues = self._check_settings_conflict(content)
            issues.extend(setting_issues)
            checked_items += 1
        
        # 5. 使用 LLM 进行深度检查
        llm_issues = self._llm_deep_check(content, previous_content)
        issues.extend(llm_issues)
        checked_items += 1
        
        # 生成摘要
        passed = len([i for i in issues if i.severity in [IssueSeverity.HIGH, IssueSeverity.CRITICAL]]) == 0
        summary = self._generate_summary(issues, passed)
        
        return CheckResult(
            passed=passed,
            issues=issues,
            summary=summary,
            checked_items=checked_items
        )
        
    def update_states_from_content(self, content: str):
        """分析章节内容，提取并更新人物的最新状态（受伤、财力、能力觉醒、位置等）"""
        known_names = self.settings_store.get_character_names()
        if not known_names:
            return
            
        prompt = f"""作为设定集记录员，请阅读以下最新章节，提取出场人物的【最新状态变化】。
关注以下方面：
1. 身体状态（受伤、中毒、痊愈等）
2. 财富/地位变化（破产、升职、获得巨款）
3. 能力/修为变化（突破、获得神器、能力被废）
4. 关键位置或心理状态变动

【已知人物列表】
{", ".join(known_names)}

【最新章节内容】
{content[:4000]}

请严格按以下JSON格式输出，只包含有状态变化的人物：
```json
[
  {{"name": "人物名", "state": "简短的一句话描述其最新状态，例如：右臂骨折，目前在医院昏迷；刚获得100万投资。"}}
]
```
如果没有状态变化，输出空数组 []。"""

        try:
            result = self.llm.generate(prompt, max_tokens=1024)
            json_match = re.search(r'```json\s*(.*?)\s*```', result, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                data = json.loads(result)
                
            if isinstance(data, list):
                for item in data:
                    name = item.get("name")
                    state = item.get("state")
                    if name and state:
                        # 确保不超字数
                        self.settings_store.update_character_state(name, state[:100])
        except Exception as e:
            print(f"提取人物状态失败: {e}")

    
    def _check_character_names(self, content: str) -> List[ConsistencyIssue]:
        """检查人物名称一致性"""
        issues = []
        
        known_names = self.settings_store.get_character_names()
        if not known_names:
            return issues
        
        # 使用 LLM 检测内容中的人物名
        prompt = f"""请从以下内容中提取所有人物名称，每行一个。
只输出名称，不需要其他说明。

【内容】
{content[:3000]}

【人物名称】"""
        
        result = self.llm.generate(prompt, max_tokens=512)
        found_names = [n.strip() for n in result.split('\n') if n.strip()]
        
        # 检查是否有相似但不同的名称（可能是笔误）
        for found in found_names:
            if found not in known_names:
                # 检查是否是已知角色的变体
                for known in known_names:
                    if self._is_similar_name(found, known):
                        issues.append(ConsistencyIssue(
                            type=IssueType.CHARACTER_NAME,
                            severity=IssueSeverity.MEDIUM,
                            description=f"人物名称可能不一致：'{found}' 与已知角色 '{known}' 相似",
                            location=f"当前章节",
                            suggestion=f"请确认 '{found}' 是否应该写作 '{known}'",
                            related_content=found
                        ))
                        break
        
        return issues
    
    def _is_similar_name(self, name1: str, name2: str) -> bool:
        """检查两个名字是否相似"""
        # 简单的相似度检查
        if len(name1) == 0 or len(name2) == 0:
            return False
        
        # 一个是另一个的子串
        if name1 in name2 or name2 in name1:
            return True
        
        # 只差一个字
        if abs(len(name1) - len(name2)) <= 1:
            common = sum(1 for a, b in zip(name1, name2) if a == b)
            if common >= min(len(name1), len(name2)) - 1:
                return True
        
        return False
    
    def _check_character_behavior(self, content: str) -> List[ConsistencyIssue]:
        """检查人物行为一致性"""
        issues = []
        
        # 获取所有角色及其性格特点
        character_info = []
        for char in self.settings_store.get_all_characters():
            if char.traits:
                character_info.append(f"- {char.name}: {', '.join(char.traits)}")
        
        if not character_info:
            return issues
        
        prompt = f"""请检查以下内容中的人物行为是否与其性格设定一致。

【人物设定】
{chr(10).join(character_info)}

【待检查内容】
{content[:3000]}

如果发现不一致，请说明：
1. 哪个人物
2. 什么行为
3. 为什么与设定不符
4. 修改建议

如果没有问题，只输出"通过"。"""
        
        result = self.llm.generate(prompt, max_tokens=1024)
        
        if "通过" not in result and len(result) > 10:
            issues.append(ConsistencyIssue(
                type=IssueType.CHARACTER_TRAIT,
                severity=IssueSeverity.MEDIUM,
                description=result[:500],
                location="当前章节",
                suggestion="请根据人物设定调整行为描写"
            ))
        
        return issues
    
    def _check_continuity(
        self,
        content: str,
        previous_content: str
    ) -> List[ConsistencyIssue]:
        """检查连续性"""
        issues = []
        
        # 取前文末尾
        prev_excerpt = previous_content[-1500:] if len(previous_content) > 1500 else previous_content
        curr_excerpt = content[:1500]
        
        prompt = f"""请检查以下两段内容的连续性，是否存在：
1. 场景突变（无过渡地切换场景）
2. 时间跳跃（时间线不连贯）
3. 人物状态矛盾（如前文受伤，后文突然痊愈）
4. 对话断裂（对话没有合理衔接）

【前文结尾】
{prev_excerpt}

【后文开头】
{curr_excerpt}

如果发现问题，请说明问题类型和具体内容。
如果衔接良好，只输出"衔接良好"。"""
        
        result = self.llm.generate(prompt, max_tokens=1024)
        
        if "衔接良好" not in result and "良好" not in result and len(result) > 20:
            issues.append(ConsistencyIssue(
                type=IssueType.CONTINUITY,
                severity=IssueSeverity.MEDIUM,
                description=result[:500],
                location="章节衔接处",
                suggestion="请添加过渡内容或修正矛盾"
            ))
        
        return issues
    
    def _check_settings_conflict(self, content: str) -> List[ConsistencyIssue]:
        """检查设定冲突"""
        issues = []
        
        world_context = self.settings_store.get_context_for_writing()
        
        prompt = f"""请检查以下内容是否与世界观设定冲突。

【世界观设定】
{world_context}

【待检查内容】
{content[:3000]}

如果发现冲突，请说明：
1. 哪条设定被违反
2. 内容中的哪部分与设定冲突
3. 修改建议

如果没有冲突，只输出"无冲突"。"""
        
        result = self.llm.generate(prompt, max_tokens=1024)
        
        if "无冲突" not in result and len(result) > 20:
            issues.append(ConsistencyIssue(
                type=IssueType.SETTING,
                severity=IssueSeverity.HIGH,
                description=result[:500],
                location="当前章节",
                suggestion="请修正与设定冲突的内容"
            ))
        
        return issues
    
    def _llm_deep_check(
        self,
        content: str,
        previous_content: str = ""
    ) -> List[ConsistencyIssue]:
        """LLM 深度检查"""
        issues = []
        
        context = ""
        if previous_content:
            context = f"\n【前文摘要】\n{previous_content[-1000:]}"
        
        prompt = f"""作为一位资深编辑，请检查以下小说内容的逻辑问题：
{context}
【待检查内容】
{content[:4000]}

请检查：
1. 是否有逻辑漏洞（前后矛盾）
2. 是否有情节不合理之处
3. 是否有明显的常识错误

如果发现问题，请简洁列出。
如果没有明显问题，输出"检查通过"。"""
        
        result = self.llm.generate(prompt, max_tokens=1024)
        
        if "检查通过" not in result and "通过" not in result.lower() and len(result) > 30:
            # 解析问题
            for line in result.split('\n'):
                line = line.strip()
                if line and (line.startswith(('-', '•', '*')) or line[0].isdigit()):
                    issues.append(ConsistencyIssue(
                        type=IssueType.LOGIC,
                        severity=IssueSeverity.LOW,
                        description=line.lstrip('-•* 0123456789.'),
                        location="当前章节",
                        suggestion="请审视并修正此问题"
                    ))
        
        return issues[:5]  # 最多返回5个问题
    
    def _generate_summary(self, issues: List[ConsistencyIssue], passed: bool) -> str:
        """生成检查摘要"""
        if not issues:
            return "✅ 一致性检查通过，未发现问题。"
        
        critical = len([i for i in issues if i.severity == IssueSeverity.CRITICAL])
        high = len([i for i in issues if i.severity == IssueSeverity.HIGH])
        medium = len([i for i in issues if i.severity == IssueSeverity.MEDIUM])
        low = len([i for i in issues if i.severity == IssueSeverity.LOW])
        
        status = "⚠️ 发现问题" if passed else "❌ 检查未通过"
        
        parts = [f"{status}：共 {len(issues)} 个问题"]
        if critical:
            parts.append(f"严重 {critical}")
        if high:
            parts.append(f"高 {high}")
        if medium:
            parts.append(f"中 {medium}")
        if low:
            parts.append(f"低 {low}")
        
        return " | ".join(parts)
    
    def check_unresolved_foreshadowing(self, current_chapter: int) -> List[str]:
        """检查未回收的伏笔提醒"""
        reminders = []
        
        unresolved = self.settings_store.get_unresolved_plot_points()
        for point in unresolved:
            chapters_passed = current_chapter - point.introduced_chapter
            if chapters_passed >= 5:  # 超过5章未回收
                reminders.append(
                    f"伏笔提醒：'{point.description}' 已埋下 {chapters_passed} 章，"
                    f"考虑在近期章节回收。"
                )
        
        return reminders
    
    def format_issues_report(self, result: CheckResult) -> str:
        """格式化问题报告"""
        lines = [
            "=" * 50,
            "一致性检查报告",
            "=" * 50,
            f"检查项: {result.checked_items}",
            f"状态: {'通过' if result.passed else '未通过'}",
            f"摘要: {result.summary}",
            ""
        ]
        
        if result.issues:
            lines.append("详细问题：")
            lines.append("-" * 40)
            
            for i, issue in enumerate(result.issues, 1):
                lines.append(f"\n[{i}] {issue.type.value}")
                lines.append(f"    严重程度: {issue.severity.value}")
                lines.append(f"    位置: {issue.location}")
                lines.append(f"    描述: {issue.description}")
                lines.append(f"    建议: {issue.suggestion}")
        
    def check_full_text(self, content: str, title: str = "") -> List[ConsistencyIssue]:
        """全文连贯性检查（生成后）"""
        issues = []
        
        # 构建提示词
        prompt = self._build_fulltext_check_prompt(content, title)
        
        try:
            response = self.llm.generate(prompt)
            issues = self._parse_check_response(response)
        except Exception as e:
            print(f"全文检查失败: {e}")
            
        return issues

    def auto_fix(self, content: str, issues: List[ConsistencyIssue]) -> str:
        """自动修复内容"""
        fixed_content = content
        
        # 过滤可修复的问题
        fixable = [i for i in issues if i.auto_fixable and i.original_text and i.fixed_text]
        
        for issue in fixable:
            if issue.original_text in fixed_content:
                fixed_content = fixed_content.replace(issue.original_text, issue.fixed_text)
                
        return fixed_content

    def _build_fulltext_check_prompt(self, content: str, title: str) -> str:
        """构建全文检查提示词"""
        
        # 收集上下文信息
        context = []
        if self.settings_store:
            world_settings = self.settings_store.get_world_settings()
            if world_settings:
                context.append("【世界观设定】")
                for k, v in world_settings.items():
                    context.append(f"- {k}: {v}")
                    
            characters = self.settings_store.get_all_characters()
            if characters:
                context.append("\n【主要人物】")
                for name, info in characters.items():
                    context.append(f"- {name}: {info['description']}")
                    if info['traits']:
                        context.append(f"  性格: {', '.join(info['traits'])}")
        
        context_str = "\n".join(context) if context else "无可用设定信息"
        
        default_prompt = f"""你是一个专业的文学编辑和逻辑审核员。请对以下小说/文章内容进行深度的逻辑与一致性检查。
你的任务是找出内容中存在的冲突、漏洞和不合理之处。

【已知设定参考】
{context_str}

【待检查内容】
作品名：{title}
{content}

请检查以下方面：
1. 人物名称或称呼前后不一致（如把“张三”写成“李四”）
2. 人物性格或能力与设定冲突（如普通人突然会魔法，除非有合理解释）
3. 时间线逻辑错误（如时间倒流、事件顺序冲突）
4. 设定冲突（与已知设定的物理定律、地理位置、力量体系冲突）
5. 情节漏洞（未填的坑、缺乏逻辑的突发事件）
6. 连续性（前后文衔接不自然，场景/动作跳跃）

请以 JSON 格式输出检查结果，格式要求如下：
{{
  "passed": false, // 如果没有发现任何问题则为 true
  "issues": [      // 如果通过，此数组可以为空
    {{
      "type": "类型（例如：人物名称不一致、时间线矛盾、情节漏洞等）",
      "severity": "严重程度（低/中/高/严重）",
      "location": "问题出现的具体位置片段或段落",
      "description": "详细描述问题是什么，为什么是不合理的",
      "suggestion": "提供修改建议"
    }}
  ],
  "summary": "整体评价和审核总结（50-100字）"
}}

约束条件：
1. 只输出有效的 JSON，不要包含任何 markdown 标记（如 ```json）或额外说明文本。
2. 确保输出可以被 JSON 解析器直接解析。
3. 如果没有发现问题，也要严格按照 JSON 格式返回 passed: true。
"""
        template = self.prompts.get("deep_check", default_prompt)
        try:
            return template.format(context_str=context_str, title=title, content=content)
        except Exception:
            return default_prompt

    def _parse_check_response(self, response: str) -> List[ConsistencyIssue]:
        """解析检查响应"""
        issues = []
        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                data = json.loads(response)
            
            raw_issues = data.get("issues", [])
            summary = data.get("summary", "")
            
            # 映射类型 string 到 enum
            type_map = {
                "人物一致性": IssueType.CHARACTER_TRAIT,
                "情节逻辑": IssueType.LOGIC,
                "时间线": IssueType.TIMELINE,
                "场景设定": IssueType.SETTING,
                "伏笔回收": IssueType.PLOT_HOLE
            }
            
            severity_map = {
                "高": IssueSeverity.HIGH,
                "中": IssueSeverity.MEDIUM,
                "低": IssueSeverity.LOW
            }
            
            for item in raw_issues:
                issue_type = type_map.get(item.get("type"), IssueType.CONTINUITY)
                severity = severity_map.get(item.get("severity"), IssueSeverity.MEDIUM)
                
                issues.append(ConsistencyIssue(
                    type=issue_type,
                    severity=severity,
                    description=item.get("description", ""),
                    location=item.get("location", ""),
                    suggestion=item.get("suggestion", ""),
                    original_text=item.get("original", ""),
                    fixed_text=item.get("fixed", ""),
                    auto_fixable=bool(item.get("original") and item.get("fixed"))
                ))
                
        except Exception as e:
            print(f"解析检查结果失败: {e}")
            
        return issues
