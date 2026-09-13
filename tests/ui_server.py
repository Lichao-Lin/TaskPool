from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import Api,Storage
from datetime import datetime,timedelta
root=Path(__file__).resolve().parents[1]
tmp=tempfile.TemporaryDirectory();api=Api(Storage(Path(tmp.name)/'e2e.db'))
pid=api.db.add_task('完成项目报告','报告与结果表',(datetime.now()+timedelta(days=1)).strftime('%Y-%m-%d %H:%M'),100)
api.db.add_task('整理实验数据','结果表',(datetime.now()+timedelta(days=1)).strftime('%Y-%m-%d %H:%M'),20,pid)
api.db.add_task('阅读论文','笔记',(datetime.now()+timedelta(days=4)).strftime('%Y-%m-%d %H:%M'),30)
earn=api.db.add_task('已完成的准备工作','完成',datetime.now().strftime('%Y-%m-%d %H:%M'),200);api.db.complete_task(earn)
for i,n in enumerate(['一杯咖啡','一场电影','游戏一小时','一本新书','一顿美食','周末短途旅行']):api.db.add_reward(n,'给完成工作的自己',20+i*20)
for n in ['阅读 20 分钟','运动 30 分钟','晚间复盘']:api.db.add_routine('work',n)
api.db.add_routine('rest','散步')
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):
  if self.path=='/':data=(root/'frontend.html').read_bytes();mime='text/html; charset=utf-8'
  elif self.path=='/state':data=json.dumps(api.state()).encode();mime='application/json'
  else:self.send_error(404);return
  self.send_response(200);self.send_header('Content-Type',mime);self.end_headers();self.wfile.write(data)
 def do_POST(self):
  payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
  method=self.path[1:]
  if method not in ['action','setting','change_data','background']:self.send_error(404);return
  data=json.dumps(getattr(api,method)(*payload)).encode()
  self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(data)
ThreadingHTTPServer(('127.0.0.1',8876),Handler).serve_forever()
