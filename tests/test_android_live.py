"""Opt-in installed-cache MCP smoke test; only changes the Settings search draft."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

class Client:
    def __init__(self, root):
        self.p = subprocess.Popen([sys.executable,'-u',str(root/'scripts/launch_android.py')],
                                  stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                  text=True,encoding='utf-8')
        self.responses=queue.Queue();self.errors=[];self.pending={};self.ident=0
        def read():
            for line in self.p.stdout:
                try:self.responses.put(json.loads(line))
                except ValueError:self.errors.append(line[:200])
        threading.Thread(target=read,daemon=True).start()
        threading.Thread(target=lambda:self.errors.extend(line[:200] for line in self.p.stderr),daemon=True).start()
    def send(self, method, params):
        self.ident+=1
        self.p.stdin.write(json.dumps({'jsonrpc':'2.0','id':self.ident,'method':method,'params':params},ensure_ascii=False)+'\n')
        self.p.stdin.flush();return self.ident
    def get(self, ident, timeout=40):
        if ident in self.pending:return self.pending.pop(ident)
        deadline=time.monotonic()+timeout
        while True:
            value=self.responses.get(timeout=max(.1,deadline-time.monotonic()))
            if value.get('id')==ident:return value
            self.pending[value.get('id')]=value
    def call(self,name,args=None,allow_error=False):
        result=self.get(self.send('tools/call',{'name':'android_'+name,'arguments':args or {}}))['result']
        if result.get('isError') and not allow_error:raise RuntimeError(result['content'][0]['text'])
        return result
    def close(self):
        self.p.stdin.close()
        try:self.p.wait(timeout=10)
        except subprocess.TimeoutExpired:self.p.terminate();self.p.wait(timeout=5)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run',action='store_true',help='Authorize Settings search smoke test and return Home')
    args=p.parse_args()
    if not args.run:p.error('Pass --run to explicitly opt in to live phone actions')
    state=Path(os.environ.get('ANDROID_USE_STATE_DIR',str(Path(os.environ['LOCALAPPDATA'])/'AndroidUse')))
    installed=json.loads((state/'installation.json').read_text(encoding='utf-8-sig'))
    c=Client(Path(installed['installedPath']))
    ready=False
    try:
        init=c.get(c.send('initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'android-live-smoke','version':'1'}}))
        assert init['result']['serverInfo']['name']=='android-use'
        ready=c.call('ready')['structuredContent']['ready']
        if not ready:raise RuntimeError('User must unlock phone before live validation')
        initial=c.call('observe')['structuredContent']['observation']
        print('PASS: auto observation coverage',initial['tree_quality']['status'],initial['returned_mode'],flush=True)
        launched=c.call('launch_app',{'package':'com.android.settings'})['structuredContent']
        assert launched['verification']['check']=='foreground_package'
        current=c.call('observe',{'mode':'tree'})['structuredContent']['observation']
        if not any(n.get('resource-id')=='android:id/search_src_text' for n in current['nodes']):
            found=c.call('scroll_find',{'selector':{'resourceId':'android:id/search_src_text'},'direction':'down'})['structuredContent']
            assert found['found'],'Settings search is not exposed; inspect screen instead of guessing'
        c.call('tap',{'selector':{'resourceId':'android:id/search_src_text'},
                      'verify':{'selector':{'resourceId':'android:id/search_src_text'},'timeout':3}})
        typed=c.call('type_text',{'selector':{'resourceId':'android:id/search_src_text'},'text':'蓝牙'})['structuredContent']
        assert typed['verification']['status']=='verified' and typed['verification']['check']=='text_readback'
        print('PASS: Settings navigation, Unicode input and readback',flush=True)
        bad=c.call('tap',{'selector':{'resourceId':'android:id/search_src_text'},
                          'verify':{'selector':{'resourceId':'no.such:id/control'},'timeout':0}},allow_error=True)
        assert bad['isError'] and bad['structuredContent']['executed']
        assert bad['structuredContent']['verification']['status']=='failed'
        assert bad['structuredContent']['observation']
        print('PASS: failed postcondition preserves dispatch and actual observation without replay',flush=True)
        c.call('screen')
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            frame=c.call('screen_frame')['structuredContent']
            if frame.get('frame'):break
            time.sleep(.15)
        assert frame.get('frame'),frame
        assert frame.get('source')=='scrcpy',frame.get('stream_error')
        print('PASS: scrcpy live frame',frame['frame']['width'],frame['frame']['height'],flush=True)
        wait=c.send('tools/call',{'name':'android_wait','arguments':{'selector':{'resourceId':'no.such:id/control'},'timeout':3}})
        time.sleep(.25)
        started=time.monotonic()
        frame=c.call('screen_frame')['structuredContent']
        latency=time.monotonic()-started
        assert latency<1.5,latency
        assert frame['busy']
        assert c.get(wait)['result']['isError']
        print('PASS: preview during tool wait; response seconds',round(latency,3),flush=True)
        assert c.call('screen',{'action':'pause'})['structuredContent']['paused']
        assert c.call('screen_frame')['structuredContent']['frame'] is None
        c.call('screen',{'action':'resume'})
        print('PASS: pause erases cached frame; resume accepted',flush=True)
        result=c.call('batch',{'steps':[
            {'op':'wait','args':{'selector':{'resourceId':'no.such:id/control'},'timeout':0}},
            {'op':'press_button','args':{'name':'home'}}]},allow_error=True)
        assert result['isError'] and result['structuredContent']['stopped_at']==0
        app=c.call('observe')['structuredContent']['observation']['app']['package']
        assert app=='com.android.settings',app
        print('PASS: failed batch stops before subsequent Home action',flush=True)
        c.call('setup',{'action':'reconnect'})
        assert c.call('ready')['structuredContent']['ready']
        print('PASS: explicit reconnect reuses device without replaying actions',flush=True)
    finally:
        if ready:
            try:c.call('press_button',{'name':'home'})
            except Exception:pass
        c.close()
        if c.errors:print('Server diagnostics:',c.errors[:3],flush=True)

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
