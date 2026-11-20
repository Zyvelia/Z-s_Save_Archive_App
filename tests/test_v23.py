import hashlib,json,tempfile,threading,unittest
from pathlib import Path
from zarchive.homebrew_v23 import (catalog_items,list_releases,select_newest,queue_asset,load_queue,
 update_job,recover_queue,download_queued_asset,validate_asset_url,DownloadCancelled)

class Response:
 def __init__(self,data,url='https://github.com/example/releases/download/v1/example.pkg'):
  self.data=data;self.i=0;self.url=url;self.headers={'Content-Length':str(len(data))}
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def read(self,n=-1):
  if n<0:n=len(self.data)
  b=self.data[self.i:self.i+n];self.i+=len(b);return b
 def geturl(self):return self.url
class Opener:
 def __init__(self,content):self.content=content
 def open(self,req,timeout=None):return Response(self.content)

class TestV23(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.base=Path(self.temp.name);self.path=self.base/'queue.json';self.content=b'\x7fPKG'+b'data'*30
  self.asset={'name':'app.pkg','url':'https://github.com/bucanero/apollo-ps3/releases/download/v1/app.pkg','size':len(self.content),'digest':'sha256:'+hashlib.sha256(self.content).hexdigest()}
 def queue(self):return queue_asset(self.path,'Apollo Save Tool','v1',self.asset)
 def test_catalog(self):
  a=catalog_items();self.assertTrue(len(a)>=6);self.assertTrue(any(x['auto_release'] for x in a))
 def test_no_unsafe_url(self):
  for url in ('http://github.com/abc','https://evil.example/x.pkg','https://github.com.evil.example/a','https://u:p@github.com/a'):
   with self.assertRaises(ValueError):validate_asset_url(url)
 def test_list_release_asset(self):
  data=[{'tag_name':'v1','draft':False,'prerelease':False,'assets':[{'name':'foo.pkg','size':120,'browser_download_url':self.asset['url']}]}]
  results=list_releases('Apollo Save Tool',opener=Opener(json.dumps(data).encode()))
  self.assertEqual(len(results[0]['assets']),1)
 def test_draft_ignored(self):
  data=[{'tag_name':'v1','draft':True,'assets':[]}]
  self.assertEqual(list_releases('Apollo Save Tool',opener=Opener(json.dumps(data).encode())),[])
 def test_not_github(self):
  with self.assertRaises(ValueError):list_releases('Movian')
 def test_newest(self):
  self.assertEqual(select_newest([{'prerelease':True,'assets':[1]},{'prerelease':False,'assets':[2]}])['assets'],[2])
 def test_queue_dedupe(self):
  x=self.queue();self.assertEqual(x['id'],self.queue()['id']);self.assertEqual(len(load_queue(self.path)),1)
 def test_cross_repo_asset_rejected(self):
  with self.assertRaises(ValueError):queue_asset(self.path,'Apollo Save Tool','v1',{**self.asset,'url':'https://github.com/other/repo/releases/download/v1/app.pkg'})
 def test_queue_reject_non_pkg(self):
  with self.assertRaises(ValueError):queue_asset(self.path,'Apollo Save Tool','v1',{**self.asset,'name':'x.exe'})
 def test_complete_download(self):
  x=self.queue();done=download_queued_asset(self.path,x['id'],self.base/'downloads',opener=Opener(self.content))
  self.assertEqual(done['status'],'downloaded');self.assertEqual(Path(done['local_path']).read_bytes(),self.content)
 def test_wrong_digest(self):
  x=self.queue();bad=b'\x7fPKG'+b'Z'*120
  with self.assertRaises(ValueError):download_queued_asset(self.path,x['id'],self.base/'downloads',opener=Opener(bad))
  self.assertFalse((self.base/'downloads'/'app.pkg').exists())
 def test_wrong_magic(self):
  x=self.queue();bad=b'BAD!'+self.content[4:]
  self.asset['digest']='sha256:'+hashlib.sha256(bad).hexdigest()
  update_job(self.path,x['id'],status='failed')
  with self.assertRaises(ValueError):download_queued_asset(self.path,x['id'],self.base/'downloads',opener=Opener(bad))
 def test_cancel(self):
  x=self.queue();cancel=threading.Event();cancel.set()
  with self.assertRaises(DownloadCancelled):download_queued_asset(self.path,x['id'],self.base/'downloads',opener=Opener(self.content),cancel=cancel)
  self.assertEqual(load_queue(self.path)[0]['status'],'cancelled')
 def test_recover(self):
  x=self.queue();update_job(self.path,x['id'],status='downloading')
  self.assertEqual(recover_queue(self.path)[0]['status'],'interrupted')
 def test_no_overwrite(self):
  x=self.queue();d=self.base/'downloads';d.mkdir();(d/'app.pkg').write_bytes(b'old')
  with self.assertRaises(FileExistsError):download_queued_asset(self.path,x['id'],d,opener=Opener(self.content))
  self.assertEqual((d/'app.pkg').read_bytes(),b'old')
 def test_reject_invalid_mutation(self):
  x=self.queue()
  with self.assertRaises(ValueError):update_job(self.path,x['id'],url='http://bad')

if __name__=='__main__':unittest.main()
