import tempfile,sys,unittest
from pathlib import Path
from threading import Event
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sources import discover
from engine import Store

class TestBraveTransient(unittest.TestCase):
    def test_brave_results_not_stored(self):
        class FakeHTTP:
            def get(self,*args,**kwargs):
                class Response:
                    def json(self):return {'web':{'results':[{'title':'Leak example','url':'https://x.com/anon/status/12345','description':'my source is a screener'}]}}
                return Response()
        with tempfile.TemporaryDirectory() as d:
            db=Store(Path(d)/'data.sqlite')
            gathered=[]
            discover(db,FakeHTTP(),lambda msg:None,max_queries=1,mode='brave',brave_key='test',stop=Event(),on_brave_results=lambda batch:gathered.extend(batch))
            self.assertEqual(len(gathered),1)
            self.assertEqual(db.summary()['total'],0)
            self.assertEqual(len(db.runs()),1)
            db.conn.close()
    def test_purges_old_brave_snippets(self):
        from engine import Record
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'old.sqlite'
            db=Store(path)
            db.add(Record(url='https://x.com/anon/status/123',text='old content',title='old result',source_kind='search_snippet'))
            self.assertEqual(db.summary()['total'],1)
            db.conn.close()
            db=Store(path)
            self.assertEqual(db.summary()['total'],0)
            db.conn.close()
if __name__=='__main__':unittest.main()
