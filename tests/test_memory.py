import unittest
import os
import json
from memory.context_manager import ContextManager, ChapterSummary
from memory.settings_store import SettingsStore, CharacterProfile, PlotPoint

class TestContextManager(unittest.TestCase):
    
    def setUp(self):
        self.cm = ContextManager(max_summaries=2, max_context_tokens=1000)
        self.test_file = "test_context.json"

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def test_add_chapter_summary(self):
        self.cm.add_chapter_summary(1, "第一章", "开始", 100)
        self.assertEqual(len(self.cm.summaries), 1)
        self.assertEqual(self.cm.get_total_word_count(), 100)
        
        # Test max summaries limit (compression)
        self.cm.add_chapter_summary(2, "第二章", "发展", 200)
        self.cm.add_chapter_summary(3, "第三章", "高潮", 300)
        self.assertEqual(len(self.cm.summaries), 2)
        self.assertEqual(self.cm.summaries[0].chapter_id, 2)
        self.assertEqual(self.cm.summaries[1].chapter_id, 3)

    def test_settings_and_character_state(self):
        self.cm.set_settings({"world": "magic"})
        self.assertEqual(self.cm.get_settings(), {"world": "magic"})
        
        self.cm.update_character_state("Hero", {"hp": 100})
        self.assertEqual(self.cm.get_character_state("Hero"), {"hp": 100})
        
        self.cm.update_character_state("Hero", {"mp": 50})
        self.assertEqual(self.cm.get_character_state("Hero"), {"hp": 100, "mp": 50})

    def test_save_and_load(self):
        self.cm.add_chapter_summary(1, "ch1", "s1", 100)
        self.cm.set_settings({"a": 1})
        self.cm.update_character_state("c1", {"s": 1})
        
        self.cm.save_to_file(self.test_file)
        
        new_cm = ContextManager()
        new_cm.load_from_file(self.test_file)
        
        self.assertEqual(len(new_cm.summaries), 1)
        self.assertEqual(new_cm.summaries[0].title, "ch1")
        self.assertEqual(new_cm.get_settings(), {"a": 1})
        self.assertEqual(new_cm.get_character_state("c1"), {"s": 1})


class TestSettingsStore(unittest.TestCase):
    
    def setUp(self):
        self.store = SettingsStore()
        self.test_file = "test_settings.json"

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def test_world_settings(self):
        self.store.set_world_settings({"type": "sci-fi"})
        self.store.update_world_settings("year", 2077)
        self.assertEqual(self.store.get_world_settings(), {"type": "sci-fi", "year": 2077})

    def test_character_management(self):
        self.store.add_character("Alice", "Protagonist", ["brave"], ["coding"], 1)
        char = self.store.get_character("Alice")
        self.assertIsNotNone(char)
        self.assertEqual(char.description, "Protagonist")
        self.assertEqual(char.traits, ["brave"])
        
        self.store.update_character_state("Alice", "injured")
        self.assertEqual(self.store.get_character("Alice").current_state, "injured")
        
        self.store.add_character("Bob", "Sidekick")
        self.store.add_character_relationship("Alice", "Bob", "friends")
        self.assertEqual(self.store.get_character("Alice").relationships.get("Bob"), "friends")
        
        names = self.store.get_character_names()
        self.assertIn("Alice", names)
        self.assertIn("Bob", names)

    def test_plot_points(self):
        self.store.add_plot_point("Find key", introduced_chapter=1)
        unresolved = self.store.get_unresolved_plot_points()
        self.assertEqual(len(unresolved), 1)
        pp_id = unresolved[0].id
        
        self.store.resolve_plot_point(pp_id, 2)
        self.assertEqual(len(self.store.get_unresolved_plot_points()), 0)
        
        ch1_points = self.store.get_plot_points_by_chapter(1)
        self.assertEqual(len(ch1_points), 1)
        self.assertTrue(ch1_points[0].is_resolved)
        self.assertEqual(ch1_points[0].resolved_chapter, 2)

    def test_timeline(self):
        self.store.add_timeline_event("Year 1", 1, "Start", ["Alice"])
        timeline = self.store.get_timeline()
        self.assertEqual(len(timeline), 1)
        self.assertEqual(timeline[0].timestamp, "Year 1")

    def test_save_and_load(self):
        self.store.set_world_settings({"a": 1})
        self.store.add_character("C", "Desc")
        self.store.add_plot_point("PP")
        self.store.add_timeline_event("T1", 1, "E1")
        
        self.store.save_to_file(self.test_file)
        
        new_store = SettingsStore()
        new_store.load_from_file(self.test_file)
        
        self.assertEqual(new_store.get_world_settings(), {"a": 1})
        self.assertIsNotNone(new_store.get_character("C"))
        self.assertEqual(len(new_store.get_unresolved_plot_points()), 1)
        self.assertEqual(len(new_store.get_timeline()), 1)

if __name__ == '__main__':
    unittest.main()
