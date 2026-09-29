import pathlib, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Tests(unittest.TestCase):
    def test_generator_contract(self):
        s=(ROOT/'scripts/fetch_and_build.py').read_text(encoding='utf-8')
        self.assertIn('APP_VERSION = "5.2.0"',s)
        self.assertIn('id="stockCountChip"',s)
        self.assertIn('AI 投资助手 · 正在值守',s)
        self.assertIn('Myalpha View V{APP_VERSION}',s)
    def test_assistant_normal_visibility(self):
        s=(ROOT/'docs/assets/investment-assistant.js').read_text(encoding='utf-8')
        self.assertIn('今天最重要的 3 件事',s)
        self.assertIn('AI 投资助手 · 正常值守',s)
        self.assertNotIn("if(c.mode==='normal'){root.hidden=true",s)
    def test_watchlist_count_sync(self):
        s=(ROOT/'docs/assets/stock-watchlist.js').read_text(encoding='utf-8')
        self.assertIn("document.getElementById('stockCountChip')",s)
        self.assertIn('assistantStatus',s)
    def test_knowledge_version_dynamic(self):
        s=(ROOT/'docs/assets/knowledge.js').read_text(encoding='utf-8')
        self.assertIn("dataset?.appVersion",s)
        self.assertNotIn('KNOWLEDGE / V4.9.3',s)
if __name__=='__main__': unittest.main()
