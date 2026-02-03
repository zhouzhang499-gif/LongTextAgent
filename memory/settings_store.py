"""
设定存储模块
管理世界观、人物、时间线等设定信息
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
import json
import os


@dataclass
class CharacterProfile:
    """人物档案"""
    name: str
    aliases: List[str] = field(default_factory=list)  # 别名
    description: str = ""
    traits: List[str] = field(default_factory=list)  # 性格特点
    abilities: List[str] = field(default_factory=list)  # 能力
    relationships: Dict[str, str] = field(default_factory=dict)  # 与其他角色关系
    current_state: str = ""  # 当前状态
    first_appearance: int = 0  # 首次出现章节


@dataclass
class PlotPoint:
    """情节点/伏笔"""
    id: int
    type: str  # 'foreshadowing', 'plot_thread', 'mystery'
    description: str
    introduced_chapter: int
    resolved_chapter: Optional[int] = None
    is_resolved: bool = False
    related_characters: List[str] = field(default_factory=list)


@dataclass
class TimelineEvent:
    """时间线事件"""
    id: int
    timestamp: str  # 故事内时间
    chapter_id: int
    description: str
    characters_involved: List[str] = field(default_factory=list)


class SettingsStore:
    """
    设定存储
    
    管理：
    1. 世界观设定
    2. 人物档案
    3. 伏笔/情节线追踪
    4. 时间线
    """
    
    def __init__(self):
        self.world_settings: Dict[str, Any] = {}  # 世界观设定
        self.characters: Dict[str, CharacterProfile] = {}  # 人物档案
        self.plot_points: List[PlotPoint] = []  # 伏笔/情节点
        self.timeline: List[TimelineEvent] = []  # 时间线
        
        self._plot_id_counter = 0
        self._timeline_id_counter = 0
    
    # ==================== 世界观设定 ====================
    
    def set_world_settings(self, settings: Dict[str, Any]):
        """设置世界观"""
        self.world_settings = settings
    
    def update_world_settings(self, key: str, value: Any):
        """更新世界观设定"""
        self.world_settings[key] = value
    
    def get_world_settings(self) -> Dict[str, Any]:
        """获取世界观设定"""
        return self.world_settings
    
    # ==================== 人物管理 ====================
    
    def add_character(
        self,
        name: str,
        description: str = "",
        traits: List[str] = None,
        abilities: List[str] = None,
        first_appearance: int = 0
    ) -> CharacterProfile:
        """添加人物"""
        profile = CharacterProfile(
            name=name,
            description=description,
            traits=traits or [],
            abilities=abilities or [],
            first_appearance=first_appearance
        )
        self.characters[name] = profile
        return profile
    
    def get_character(self, name: str) -> Optional[CharacterProfile]:
        """获取人物档案"""
        # 先尝试精确匹配
        if name in self.characters:
            return self.characters[name]
        
        # 尝试别名匹配
        for char in self.characters.values():
            if name in char.aliases:
                return char
        
        return None
    
    def update_character_state(self, name: str, state: str):
        """更新人物状态"""
        char = self.get_character(name)
        if char:
            char.current_state = state
    
    def add_character_relationship(
        self,
        character1: str,
        character2: str,
        relationship: str
    ):
        """添加人物关系"""
        char = self.get_character(character1)
        if char:
            char.relationships[character2] = relationship
    
    def get_all_characters(self) -> List[CharacterProfile]:
        """获取所有人物"""
        return list(self.characters.values())
    
    def get_character_names(self) -> List[str]:
        """获取所有人物名称（包括别名）"""
        names = []
        for char in self.characters.values():
            names.append(char.name)
            names.extend(char.aliases)
        return names
    
    # ==================== 伏笔/情节点 ====================
    
    def add_plot_point(
        self,
        description: str,
        type: str = "foreshadowing",
        introduced_chapter: int = 0,
        related_characters: List[str] = None
    ) -> PlotPoint:
        """添加伏笔/情节点"""
        self._plot_id_counter += 1
        point = PlotPoint(
            id=self._plot_id_counter,
            type=type,
            description=description,
            introduced_chapter=introduced_chapter,
            related_characters=related_characters or []
        )
        self.plot_points.append(point)
        return point
    
    def resolve_plot_point(self, plot_id: int, resolved_chapter: int):
        """标记伏笔已回收"""
        for point in self.plot_points:
            if point.id == plot_id:
                point.is_resolved = True
                point.resolved_chapter = resolved_chapter
                break
    
    def get_unresolved_plot_points(self) -> List[PlotPoint]:
        """获取未回收的伏笔"""
        return [p for p in self.plot_points if not p.is_resolved]
    
    def get_plot_points_by_chapter(self, chapter_id: int) -> List[PlotPoint]:
        """获取某章节相关的伏笔"""
        return [
            p for p in self.plot_points 
            if p.introduced_chapter == chapter_id or p.resolved_chapter == chapter_id
        ]
    
    # ==================== 时间线 ====================
    
    def add_timeline_event(
        self,
        timestamp: str,
        chapter_id: int,
        description: str,
        characters_involved: List[str] = None
    ) -> TimelineEvent:
        """添加时间线事件"""
        self._timeline_id_counter += 1
        event = TimelineEvent(
            id=self._timeline_id_counter,
            timestamp=timestamp,
            chapter_id=chapter_id,
            description=description,
            characters_involved=characters_involved or []
        )
        self.timeline.append(event)
        return event
    
    def get_timeline(self) -> List[TimelineEvent]:
        """获取完整时间线"""
        return sorted(self.timeline, key=lambda e: e.chapter_id)
    
    # ==================== 上下文生成 ====================
    
    def get_context_for_writing(self) -> str:
        """生成用于写作的设定上下文"""
        parts = []
        
        # 世界观
        if self.world_settings:
            world_text = self._format_world_settings()
            parts.append(f"【世界观】\n{world_text}")
        
        # 主要人物
        if self.characters:
            chars_text = self._format_characters()
            parts.append(f"【主要人物】\n{chars_text}")
        
        # 未回收的伏笔
        unresolved = self.get_unresolved_plot_points()
        if unresolved:
            plot_text = "\n".join([
                f"- {p.description} (第{p.introduced_chapter}章埋下)"
                for p in unresolved[-5:]  # 最多显示5个
            ])
            parts.append(f"【待回收的伏笔】\n{plot_text}")
        
        return "\n\n".join(parts)
    
    def _format_world_settings(self) -> str:
        """格式化世界观设定"""
        lines = []
        for key, value in self.world_settings.items():
            if isinstance(value, str):
                lines.append(f"- {key}: {value}")
            elif isinstance(value, list):
                lines.append(f"- {key}: {', '.join(str(v) for v in value)}")
            elif isinstance(value, dict):
                lines.append(f"- {key}:")
                for k, v in value.items():
                    lines.append(f"  - {k}: {v}")
        return "\n".join(lines)
    
    def _format_characters(self) -> str:
        """格式化人物信息"""
        lines = []
        for char in list(self.characters.values())[:10]:  # 最多10个主要人物
            char_info = f"- {char.name}"
            if char.description:
                char_info += f": {char.description}"
            if char.current_state:
                char_info += f" (当前: {char.current_state})"
            lines.append(char_info)
        return "\n".join(lines)
    
    # ==================== 持久化 ====================
    
    def save_to_file(self, filepath: str):
        """保存到文件"""
        data = {
            'world_settings': self.world_settings,
            'characters': {
                name: {
                    'name': char.name,
                    'aliases': char.aliases,
                    'description': char.description,
                    'traits': char.traits,
                    'abilities': char.abilities,
                    'relationships': char.relationships,
                    'current_state': char.current_state,
                    'first_appearance': char.first_appearance
                }
                for name, char in self.characters.items()
            },
            'plot_points': [
                {
                    'id': p.id,
                    'type': p.type,
                    'description': p.description,
                    'introduced_chapter': p.introduced_chapter,
                    'resolved_chapter': p.resolved_chapter,
                    'is_resolved': p.is_resolved,
                    'related_characters': p.related_characters
                }
                for p in self.plot_points
            ],
            'timeline': [
                {
                    'id': e.id,
                    'timestamp': e.timestamp,
                    'chapter_id': e.chapter_id,
                    'description': e.description,
                    'characters_involved': e.characters_involved
                }
                for e in self.timeline
            ],
            'plot_id_counter': self._plot_id_counter,
            'timeline_id_counter': self._timeline_id_counter
        }
        
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def load_from_file(self, filepath: str):
        """从文件加载"""
        if not os.path.exists(filepath):
            return
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.world_settings = data.get('world_settings', {})
        
        self.characters = {}
        for name, char_data in data.get('characters', {}).items():
            self.characters[name] = CharacterProfile(**char_data)
        
        self.plot_points = [
            PlotPoint(**p) for p in data.get('plot_points', [])
        ]
        
        self.timeline = [
            TimelineEvent(**e) for e in data.get('timeline', [])
        ]
        
        self._plot_id_counter = data.get('plot_id_counter', 0)
        self._timeline_id_counter = data.get('timeline_id_counter', 0)
