import os, sys, tempfile, unittest, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import canonical_url, analyze, Store, Record, export
from sources import query_set, import_records, bing_rss, bluesky_public, hackernews_public

class TestCore(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Store(Path(self.tmp.name)/'test.sqlite')
    def tearDown(self):
        self.db.conn.close();self.tmp.cleanup()
    def test_canonical_x(self):
        self.assertEqual(canonical_url('https://twitter.com/d0nut2x/status/123?s=20&utm_source=foo'), 'https://x.com/d0nut2x/status/123')
    def test_canonical_reddit_comment(self):
        self.assertEqual(canonical_url('https://www.reddit.com/r/bleach/comments/abc123/episode/def456/?utm_source=reddit'), 'https://www.reddit.com/comments/abc123/_/def456')
    def test_invalid_url(self): self.assertEqual(canonical_url('javascript:alert(1)'), '')
    def test_questions(self):
        for x in ['How did you watch the episode early?', 'comment tu as accès à l’épisode en avance ?', 'どうやって先行視聴した？']:
            self.assertTrue(analyze(x)['question'],x)
    def test_access(self):
        self.assertTrue(analyze('I got an early access screener from my contact')['access'])
    def test_denial(self):
        a=analyze("I don't have access to any screener or episode")
        self.assertTrue(a['denial']);self.assertFalse(a['firsthand'])
    def test_snippet_verification(self):
        a=analyze('My source has a screener episode',source_kind='search_snippet')
        self.assertTrue('NON VÉRIFIÉ' in a['verification']);self.assertLessEqual(a['score'],45)
    def test_dedup(self):
        r=Record(url='https://x.com/joe/status/123?ref_src=foo',text='How did you watch the episode?')
        self.assertTrue(self.db.add(r))
        self.assertFalse(self.db.add(Record(url='https://twitter.com/joe/status/123',text='How did you watch the episode?')))
        self.assertEqual(self.db.summary()['total'],1)
    def test_richer_not_overwritten(self):
        self.db.add(Record(url='https://x.com/some/status/4',text='Long specific content with early screener',source_kind='import'))
        self.db.add(Record(url='https://x.com/some/status/4',text='index',source_kind='search_snippet'))
        self.assertIn('Long specific',self.db.rows()[0]['text'])
    def test_json_import_relations(self):
        p=Path(self.tmp.name)/'in.json'
        data=[{'platform':'reddit','url':'https://www.reddit.com/r/a/comments/aaa/a/bbb/','text':'How did you get access to the episode early?', 'external_id':'t1_bbb'},
            {'platform':'reddit','url':'https://www.reddit.com/r/a/comments/aaa/a/ccc/','text':'I got an episode screener','external_id':'t1_ccc','parent_ref':'t1_bbb'}]
        p.write_text(json.dumps(data),encoding='utf-8')
        self.assertEqual(import_records(p,self.db),2)
        self.assertEqual(len(self.db.rows()),2)
        # Export is separate global target: use helper by temporarily redirecting OUTPUT for test.
        import engine
        old=engine.OUTPUT
        engine.OUTPUT=Path(self.tmp.name)
        try:
            page=export(self.db).read_text(encoding='utf-8')
            self.assertIn('Question</a> →',page)
            self.assertIn('MESSAGE FOURNI',page)
        finally:engine.OUTPUT=old
    def test_query_diversity(self):
        qs=query_set()
        self.assertGreaterEqual(len(qs),80)
        self.assertTrue(any('先行' in q for q in qs))
        self.assertTrue(any('reddit.com' in q for q in qs))
    def test_csv_formula_safe(self):
        self.db.add(Record(url='https://example.org/post',text='=HYPERLINK("bad")',title='=1+1'))
        import engine
        old=engine.OUTPUT;engine.OUTPUT=Path(self.tmp.name)
        try:
            export(self.db)
            b=(Path(self.tmp.name)/'preuves.csv').read_text(encoding='utf-8-sig')
            self.assertIn("'=1+1",b)
        finally:engine.OUTPUT=old
    def test_fake_rss_parse(self):
        class Fake:
            def get(self,*args,**kw):
                class R: content=b'<rss><channel><item><title>Bleach episode source</title><link>https://x.com/d0nut2x/status/111</link><description>early leak</description></item></channel></rss>'
                return R()
        batch=bing_rss(Fake(),'bleach')
        self.assertEqual(len(batch),1);self.assertEqual(batch[0].platform,'x')
    def test_fake_bluesky(self):
        class Fake:
            def get(self,*args,**kwargs):
                class R:
                    def json(self):return {'posts':[{'uri':'at://did:plc:123/app.bsky.feed.post/rkey','author':{'handle':'tester.bsky.social'},'record':{'text':'How did you watch the episode early?', 'createdAt':'2026-10-16','reply':{'parent':{'uri':'at://did:plc:999/app.bsky.feed.post/parent'}}}}]}
                return R()
        from threading import Event
        bluesky_public(self.db,Fake(),lambda x:None,Event(),max_queries=1)
        self.assertEqual(self.db.rows()[0]['external_id'],'at://did:plc:123/app.bsky.feed.post/rkey')
    def test_fake_hackernews(self):
        class Fake:
            def get(self,*args,**kwargs):
                class R:
                    def json(self):return {'hits':[{'objectID':'123','comment_text':'Bleach early screener from insider', 'author':'person','story_title':'Anime'}]}
                return R()
        from threading import Event
        hackernews_public(self.db,Fake(),lambda x:None,Event())
        self.assertEqual(self.db.summary()['total'],1)
if __name__=='__main__':unittest.main()

class TestSafety(unittest.TestCase):
    def test_rate_limit_stops(self):
        from sources import HTTP,LimitStop
        class R:
            status_code=429
            headers={'Retry-After':'45'}
            content=b''
        class S:
            def get(self,*args,**kwargs):return R()
        h=HTTP();h.session=S()
        with self.assertRaises(LimitStop):h.get('https://example.com/safe')
    def test_reddit_48h_expiry(self):
        from engine import Store, Record
        import sqlite3
        with tempfile.TemporaryDirectory() as p:
            path=Path(p)/'a.db'
            db=Store(path)
            db.add(Record(url='https://reddit.com/r/a/comments/aa/b/cc/',text='Some text',platform='reddit',source_kind='official_api'))
            db.conn.execute("UPDATE records SET fetched_at='2020-01-01T00:00:00+00:00'")
            db.conn.commit();db.conn.close()
            db=Store(path)
            self.assertEqual(db.summary()['total'],0)
            db.conn.close()
    def test_refuse_invalid_evidence_url(self):
        from engine import Store,Record
        with tempfile.TemporaryDirectory() as d:
            db=Store(Path(d)/'x.sqlite')
            self.assertFalse(db.add(Record(url='file:///etc/shadow',text='secret')))
            db.conn.close()
