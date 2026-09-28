import copy
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import update_wenxuecity as w

AUTHOR={'id':'brightline','name':'BrightLine','blog_id':'82458','blog_url':'https://blog.wenxuecity.com/myoverview/82458/','forum_names':['BrightLine']}
URL='https://blog.wenxuecity.com/myblog/82458/202609/3770.html'
LIST='<a href="'+URL+'">研究文章</a><a href="'+URL+'">阅读全文</a>'
BLOG='''<a href="https://passport.wenxuecity.com/members/index.php?act=profile&cid=BrightLine">BrightLine</a><div>正文</div><h1>研究文章</h1><p>(2026-09-06 08:59:48)</p><p>作者长期研究公司，强调风险控制，关注客户和盈利数据。</p><p>[</p><a>打印</a><p>]</p><div>评论</div><p>不应进入正文的留言</p>'''
FORUM='''<h1>关注风险</h1><div>来源: <a>BrightLine</a> 于 2026-09-25 12:00:00</div><a>当前最热讨论主题</a><p>今日观察公司收入与现金流，尚未形成交易规则。</p><h3>所有跟帖</h3><p>其他人建议买入，不应进入正文。</p>'''
class Analyst:
 def __init__(self):self.calls=0
 def analyze(self,item,text):
  self.calls+=1
  return {k:'原创归纳，未核验事实。' for k in w.ANALYSIS_KEYS},'ai_unverified'
class Fetcher:
 blocked=set()
 def __init__(self,mapping=None,error=None):self.mapping=mapping or {};self.error=error
 def get(self,url):
  if self.error:raise RuntimeError(self.error)
  return self.mapping[url]
class Tests(unittest.TestCase):
 def test_listing_dedup_and_identity(self):
  items,n=w.parse_listing(LIST,AUTHOR['blog_url'],'blog',[AUTHOR]);self.assertEqual(len(items),1);self.assertEqual(items[0]['author'],'BrightLine')
  raw='''<a href="/cfzh/100.html">主贴</a> - <a href="https://passport.wenxuecity.com/members/index.php?act=profile&cid=BrightLine">BrightLine</a><a href="/cfzh/101.html">别人的帖子</a> - <a href="https://passport.wenxuecity.com/members/index.php?act=profile&cid=Other">Other</a><a href="/cfzh/102.html">作者的回复</a> - <a href="https://passport.wenxuecity.com/members/index.php?act=profile&cid=BrightLine">BrightLine</a><a href="/cfzh/index.html?page=2">下一页</a>'''
  rows,n=w.parse_listing(raw,'https://bbs.wenxuecity.com/cfzh/','forum',[AUTHOR]);self.assertEqual([x['title'] for x in rows],['主贴','作者的回复']);self.assertTrue(n.endswith('page=2'))
 def test_body_excludes_comments(self):
  item={'kind':'blog','url':URL,'author':'BrightLine','title':'研究文章'}
  parsed=w.parse_article(BLOG,item);self.assertNotIn('留言',parsed['text']);self.assertEqual(parsed['published_raw'],'2026-09-06 08:59:48')
  parsed=w.parse_article(FORUM,dict(item,kind='forum'));self.assertNotIn('其他人',parsed['text'])
  with self.assertRaises(ValueError):w.parse_article(FORUM.replace('BrightLine','Other'),dict(item,kind='forum'))
 def test_fail_closed(self):
  for url in ['http://evil.test','https://blog.wenxuecity.com.evil.test/a','https://user@blog.wenxuecity.com/a']:
   with self.assertRaises(ValueError):w.canonical(url)
  with self.assertRaises(ValueError):w.parse_listing('<html>captcha</html>',AUTHOR['blog_url'],'blog',[AUTHOR])
 def test_revisions_and_no_duplicate_analysis(self):
  items={};a=Analyst();item={'kind':'blog','url':URL,'author':'BrightLine','title':'研究文章'};parsed=w.parse_article(BLOG,item)
  key,new,changed=w.upsert(items,item,parsed,a,'t1');self.assertTrue(new)
  w.upsert(items,item,parsed,a,'t2');self.assertEqual(a.calls,1)
  parsed['text']+=' 增加新判断。';w.upsert(items,item,parsed,a,'t3');self.assertEqual(a.calls,2);self.assertEqual(len(items[key]['revisions']),1)
  self.assertNotIn('text',items[key]);self.assertNotIn('body',items[key])
 def test_error_preserves_previous_articles(self):
  state=json.loads((ROOT/'docs/data/wenxuecity.json').read_text());previous=copy.deepcopy(state['articles'])
  config={'authors':[AUTHOR],'forums':['https://bbs.wenxuecity.com/cfzh/']}
  _,_,reports=w.collect(state,config,'blog',Fetcher(error='HTTP 403'),Analyst(),'now')
  self.assertEqual(state['articles'],sorted(previous,key=lambda x:(x.get('published_raw',''),x['id']),reverse=True));self.assertEqual(reports[0]['status'],'error');self.assertIsNone(reports[0]['last_success_at'])
 def test_collect_and_digest_immutable(self):
  state={'articles':[],'sources':[]};config={'authors':[AUTHOR],'forums':[]}
  new,changed,reports=w.collect(state,config,'blog',Fetcher({AUTHOR['blog_url']:LIST,URL:BLOG}),Analyst(),'now')
  self.assertEqual(len(new),1);self.assertEqual(reports[0]['status'],'ok')
  digest=w.make_digest(state,'2026-09-25',new,[],reports,'now');old=digest['article_snapshots'][0]['title'];state['articles'][0]['title']='changed'
  self.assertEqual(digest['article_snapshots'][0]['title'],old);self.assertTrue(digest['baseline'])
 def test_empty_success_is_not_error(self):
  state={'articles':[],'sources':[],'forum_baseline_at':'past'}
  d=w.make_digest(state,'2026-09-25',[],[],[{'status':'error'}],'now');self.assertEqual(d['status'],'error');self.assertNotIn('forum_last_check_at',state)
  d=w.make_digest(state,'2026-09-25',[],[],[{'status':'ok'}],'later');self.assertIn('未发现新增',d['note'])
 def test_analysis_schema(self):
  with self.assertRaises(ValueError):w.validate_analysis({'author_view':'buy'})
  self.assertEqual(len(w.validate_analysis({k:'未提供' for k in w.ANALYSIS_KEYS})),5)
 @unittest.skipUnless(importlib.util.find_spec('pandas_market_calendars'),'calendar dependency unavailable locally')
 def test_calendar_dst_holiday_early_close(self):
  for text,expected in [('2026-09-28T20:40:00+00:00','2026-09-28'),('2026-09-28T19:40:00+00:00',None),('2026-12-01T20:40:00+00:00',None),('2026-12-01T21:40:00+00:00','2026-12-01'),('2026-12-25T21:40:00+00:00',None),('2026-11-27T18:40:00+00:00','2026-11-27')]:
   self.assertEqual(w.close_window(dt.datetime.fromisoformat(text)),expected)

 def test_archive_year_count(self):
  raw='<div>2026 (129)</div><a href="/myblog/82458/202609/100.html">文章</a>'
  self.assertEqual(w.archive_year_count(raw, 2026),129)
  self.assertEqual(w.article_year({'url':'https://blog.wenxuecity.com/myblog/82458/202609/100.html'}),2026)
if __name__=='__main__':unittest.main()
