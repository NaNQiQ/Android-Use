import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
import time
from unittest.mock import patch
from unittest.mock import MagicMock
import io
import os
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('android_use', ROOT / 'server/android_use.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class Fake:
    def __init__(self): self.presses=[]
    def press(self,name):self.presses.append(name)
    def window_size(self): return 100, 200
    def dump_hierarchy(self):
        return '<hierarchy><node text="中文" bounds="[0,0][50,20]"/><node clickable="true"/></hierarchy>'
    def app_current(self): return {'package': 'test.app'}
    def screenshot(self):
        from PIL import Image
        return Image.new('RGB', self.window_size())
    def __call__(self, **kwargs):
        return type('Target', (), {'count': 2, 'wait':lambda self,timeout:False})()

class Tests(unittest.TestCase):
    def setUp(self):
        self.r = m.Runtime('fake'); self.r.d = Fake()
        self.r.connect = lambda: self.r.d
        self.r.locked = lambda:False
    def test_coordinate_bounds(self):
        for p in ((100, 0), (-1, 0), (0, 200), (float('nan'), 0)):
            with self.assertRaises(ValueError): self.r.point(*p)
        self.assertEqual(self.r.point(99, 199), (99, 199))
    def test_ambiguous_selector_rejected(self):
        with self.assertRaises(ValueError): self.r.select({'text': '中文'})
    def test_compact_tree(self):
        self.assertEqual(len(self.r.tree()['nodes']), 2)
        self.assertEqual(self.r.tree()['nodes'][0]['text'], '中文')
    def test_preview_does_not_query_phone_per_frame(self):
        self.r.health={'locked':False,'online':True}
        self.r.preview_viewport={'width':100,'height':200}
        self.r.stream=MagicMock()
        self.r.stream.snapshot.return_value={'frame':None,'viewport':{'width':50,'height':100}}
        self.r.connect=MagicMock(side_effect=AssertionError('Preview queried Android'))
        self.assertEqual(self.r.preview()['viewport'],{'width':100,'height':200})
    def test_text_input_reads_target_info_once(self):
        class Target:
            reads=0
            value=''
            @property
            def info(target):
                target.reads+=1
                return {'className':'android.widget.EditText','bounds':{'left':0,'top':0,'right':50,'bottom':20}}
            def set_text(target,text): target.value=text
            def get_text(target): return target.value
        target=Target()
        self.r.select=lambda selector:target
        self.r.d.dump_hierarchy=lambda:'<hierarchy>'+('<node text="row" bounds="[0,0][50,20]"/>'*100)+'</hierarchy>'
        with patch.object(m.time,'sleep'):
            result=self.r.call('android_type_text',{'selector':{'className':'android.widget.EditText'},'text':'中文'})
        self.assertTrue(result['executed'])
        self.assertEqual(target.reads,1)
        self.assertEqual(target.value,'中文')
    def test_fast_text_input_still_rejects_password_field(self):
        target=MagicMock()
        target.info={'className':'android.widget.EditText','bounds':{'left':0,'top':0,'right':50,'bottom':20}}
        self.r.select=lambda selector:target
        self.r.d.dump_hierarchy=lambda:'<hierarchy><node password="true" bounds="[0,0][50,20]"/></hierarchy>'
        with self.assertRaisesRegex(ValueError,'Password field requires user takeover'):
            self.r.call('android_type_text',{'selector':{'className':'android.widget.EditText'},'text':'test'})
        target.set_text.assert_not_called()
        target.get_text.assert_not_called()
    def test_invalid_arguments_are_tool_errors(self):
        self.assertTrue(m.tool_result(self.r, {'name': 'android_tap', 'arguments': {'bad': True}})['isError'])
    def test_ready_and_screen_reuse_widget_session(self):
        with patch.object(self.r, 'call', return_value={'ready':True}):
            ready=m.tool_result(self.r, {'name':'android_ready'})
            screen=m.tool_result(self.r, {'name':'android_screen'})
        self.assertEqual(ready['_meta'], screen['_meta'])
        self.assertEqual(ready['_meta']['openai/widgetSessionId'], 'android-use-screen-v0.2.3')
    def test_preview_frame_has_no_redundant_text_content(self):
        with patch.object(self.r, 'call', return_value={'frame':{'seq':1}}):
            result=m.tool_result(self.r, {'name':'android_screen_frame'})
        self.assertEqual(result['content'], [])
        self.assertEqual(result['structuredContent']['frame']['seq'], 1)
    def test_encoder_replaces_pending_pictures_while_busy(self):
        from android_stream import ScreenStream
        stream=ScreenStream('fake'); entered=threading.Event();release=threading.Event();latest=threading.Event()
        seen=[]
        def publish(image):
            seen.append(image)
            if image==1: entered.set();release.wait(2)
            if image==3:latest.set()
        stream.publish=publish
        worker=threading.Thread(target=stream.encode_latest)
        worker.start()
        try:
            stream.queue_picture(MagicMock(to_image=lambda:1))
            self.assertTrue(entered.wait(2))
            stream.queue_picture(MagicMock(to_image=lambda:2))
            stream.queue_picture(MagicMock(to_image=lambda:3))
            release.set()
            self.assertTrue(latest.wait(2))
            self.assertEqual(seen,[1,3])
        finally:
            release.set()
            with stream.encode_condition:
                stream.encoder_done=True;stream.encode_condition.notify()
            worker.join(2)
        self.assertFalse(worker.is_alive())
    def test_stale_rotated_observation_is_rejected(self):
        ident=self.r.tree()['observation_id']
        self.r.d.window_size=lambda:(200,100)
        with self.assertRaises(ValueError):self.r.validate_observation(ident)
        self.assertEqual(self.r.d.presses,[])
    def test_auto_observation_attaches_image_when_app_labels_missing(self):
        self.r.d.dump_hierarchy=lambda:'<hierarchy><node package="com.android.systemui" text="12:00" bounds="[0,0][50,20]"/></hierarchy>'
        result=self.r.call('android_observe',{})
        self.assertEqual(result['observation']['tree_quality']['status'],'unavailable')
        self.assertFalse(result['observation']['tree_quality']['complete'])
        self.assertEqual(result['image']['type'],'image')
    def test_auto_usable_tree_avoids_image_but_never_claims_complete(self):
        self.r.d.dump_hierarchy=lambda:'<hierarchy>'+''.join(
            f'<node text="row {i}" bounds="[0,{50+i*20}][50,{65+i*20}]"/>' for i in range(3))+'</hierarchy>'
        self.r.image=MagicMock(side_effect=AssertionError('Unneeded screenshot'))
        result=self.r.call('android_observe',{})
        self.assertEqual(result['observation']['tree_quality']['status'],'usable')
        self.assertFalse(result['observation']['tree_quality']['complete'])
        self.assertIsNone(result['image'])
    def test_same_package_activity_change_invalidates_coordinate_observation(self):
        self.r.d.app_current=lambda:{'package':'test.app','activity':'Editor'}
        ident=self.r.tree()['observation_id']
        self.r.d.app_current=lambda:{'package':'test.app','activity':'List'}
        with self.assertRaisesRegex(ValueError,'stale'):
            self.r.validate_observation(ident)
    def test_same_activity_content_change_invalidates_coordinate_observation(self):
        ident=self.r.tree()['observation_id']
        self.r.d.dump_hierarchy=lambda:'<hierarchy><node text="different page" bounds="[0,0][50,20]"/></hierarchy>'
        with self.assertRaisesRegex(ValueError,'hierarchy changed'):
            self.r.validate_observation(ident)
    def test_new_read_does_not_invalidate_identical_recent_observation(self):
        ident=self.r.tree()['observation_id']
        self.r.tree()
        self.r.validate_observation(ident)
    def test_observation_registry_is_bounded(self):
        first=self.r.tree()['observation_id']
        for _ in range(16):self.r.tree()
        self.assertEqual(len(self.r.observations),16)
        with self.assertRaisesRegex(ValueError,'Unknown'):
            self.r.validate_observation(first)
    def test_coordinate_action_without_observation_is_rejected(self):
        for name,args in [('tap',{'x':10,'y':20}),('swipe',{'x1':10,'x2':10,'y1':150,'y2':50})]:
            with self.assertRaisesRegex(ValueError,'requires a fresh observation_id'):
                self.r.call('android_'+name,args)
    def test_actionable_rejects_disabled_and_offscreen_nodes(self):
        for info in [{'enabled':False,'bounds':{'left':0,'top':0,'right':10,'bottom':10}},
                     {'bounds':{'left':0,'top':201,'right':10,'bottom':210}},
                     {'visibleToUser':False,'bounds':{'left':0,'top':0,'right':10,'bottom':10}}]:
            with self.assertRaises(ValueError):self.r.actionable(type('Target',(),{'info':info})())
    def test_actionable_clips_to_visible_bounds_and_does_not_require_clickable(self):
        info={'enabled':True,'clickable':False,'bounds':{'left':-10,'top':0,'right':50,'bottom':20},
              'visibleBounds':{'left':0,'top':0,'right':25,'bottom':20}}
        self.assertEqual(self.r.actionable(type('Target',(),{'info':info})())[1],(0,0,25,20))
    def test_dispatch_without_check_is_unconfirmed_and_returns_fresh_image(self):
        self.r.d.click=MagicMock()
        ident=self.r.tree()['observation_id']
        self.r.image=MagicMock(return_value={'type':'image','data':'new-post-action'})
        result=self.r.call('android_tap',{'x':10,'y':20,'observation_id':ident})
        self.r.d.click.assert_called_once_with(10,20)
        self.r.image.assert_called_once()
        self.assertTrue(result['executed'])
        self.assertEqual(result['verification']['status'],'unconfirmed')
        self.assertEqual(result['image']['data'],'new-post-action')
    def test_failed_postcondition_keeps_dispatch_and_failure_observation(self):
        self.r.d.click=MagicMock()
        with patch.object(Fake,'__call__',lambda phone,**kw:type('Target',(),{'exists':False})()):
            ident=self.r.tree()['observation_id']
            result=m.tool_result(self.r,{'name':'android_tap','arguments':{'x':10,'y':20,'observation_id':ident,
                       'verify':{'selector':{'text':'missing'},'timeout':0}}})
            self.assertTrue(result['isError'])
            self.assertTrue(result['structuredContent']['executed'])
            self.assertEqual(result['structuredContent']['verification']['status'],'failed')
            self.assertIn('observation',result['structuredContent'])
            self.assertEqual(result['content'][1]['type'],'image')
    def test_native_toast_feedback_clears_old_cache_and_does_not_infer_success(self):
        class ToastPhone(Fake):
            last_toast='old message'
            def clear_toast(phone):phone.last_toast=None
            def click(phone,x,y):phone.last_toast='fresh transient message'
        self.r.d=ToastPhone()
        ident=self.r.tree()['observation_id']
        result=self.r.call('android_tap',{'x':10,'y':20,'observation_id':ident})
        self.assertEqual(result['feedback']['messages'],['fresh transient message'])
        self.assertEqual(result['verification']['status'],'unconfirmed')
        ident=result['observation']['observation_id']
        result=self.r.call('android_tap',{'x':10,'y':20,'observation_id':ident,
                     'verify':{'toastContains':'fresh transient','timeout':0}})
        self.assertEqual(result['verification']['status'],'verified')
        self.assertEqual(result['verification']['check'],'postcondition')
    def test_native_toast_unsupported_does_not_break_action(self):
        self.r.d.click=MagicMock()
        self.r.d.clear_toast=MagicMock(side_effect=RuntimeError('unsupported'))
        ident=self.r.tree()['observation_id']
        result=self.r.call('android_tap',{'x':10,'y':20,'observation_id':ident})
        self.assertFalse(result['feedback']['supported'])
        self.assertTrue(result['executed'])
    def test_failed_capture_does_not_erase_dispatched_action(self):
        self.r.d.click=MagicMock()
        ident=self.r.tree()['observation_id']
        self.r.capture=MagicMock(side_effect=RuntimeError('Page changed during capture'))
        result=m.tool_result(self.r,{'name':'android_tap','arguments':{'x':10,'y':20,'observation_id':ident}})
        self.assertTrue(result['isError'])
        self.assertTrue(result['structuredContent']['executed'])
        self.assertIn('observation_error',result['structuredContent'])
        self.r.d.click.assert_called_once()
    def test_batch_stops_for_visual_inspection_and_keeps_image(self):
        result=self.r.call('android_batch',{'steps':[
            {'op':'press_button','args':{'name':'back'}},
            {'op':'press_button','args':{'name':'home'}}]})
        self.assertFalse(result['complete'])
        self.assertEqual(self.r.d.presses,['back'])
        self.assertEqual(result['image']['type'],'image')
    def test_batch_keeps_last_observation_image_across_wait(self):
        self.r.verify_condition=lambda condition,messages:True
        self.r.d.__call__ = MagicMock()
        with patch.object(Fake,'__call__',lambda phone,**kw:type('Target',(),{'wait':lambda self,timeout:True})()):
            result=self.r.call('android_batch',{'steps':[
                {'op':'press_button','args':{'name':'back','verify':{'package':'test.app','timeout':0}}},
                {'op':'wait','args':{'selector':{'text':'ready'},'timeout':0}}]})
        self.assertTrue(result['complete'])
        self.assertEqual(result['image']['type'],'image')
    def test_combined_conditions_must_all_match(self):
        with patch.object(Fake,'__call__',lambda phone,**kw:type('Target',(),{'exists':False})()):
            self.assertTrue(self.r.verify_condition({'absent':{'text':'missing'},'package':'test.app'},[]))
            self.assertFalse(self.r.verify_condition({'absent':{'text':'missing'},'package':'other.app'},[]))
            self.assertFalse(self.r.verify_condition({'absent':{'text':'missing'},'toastContains':'ready'},[]))
    def test_collect_stops_without_scrolling_when_tree_lacks_body(self):
        result=self.r.call('android_collect_list',{'max_pages':3})
        self.assertEqual(result['stop_reason'],'visual_inspection_required')
        self.assertEqual(result['pages_observed'],1)
        self.assertFalse(result['complete'])
        self.assertEqual(result['image']['type'],'image')
    def test_expired_observation_is_rejected(self):
        ident=self.r.tree()['observation_id']
        self.r.observations[ident]['at']=time.monotonic()-31
        with self.assertRaises(ValueError):self.r.validate_observation(ident)
    def test_batch_stops_after_failed_wait(self):
        result=self.r.call('android_batch',{'steps':[
            {'op':'wait','args':{'selector':{'text':'missing'},'timeout':0}},
            {'op':'press_button','args':{'name':'home'}}]})
        self.assertFalse(result['complete'])
        self.assertEqual(result['stopped_at'],0)
        self.assertEqual(self.r.d.presses,[])
    def test_secure_tree_values_are_redacted(self):
        self.r.d.dump_hierarchy=lambda:'<hierarchy><node password="true" text="secret" content-desc="secret" resource-id="password"/></hierarchy>'
        node=self.r.tree()['nodes'][0]
        self.assertNotIn('text',node);self.assertNotIn('content-desc',node)
    def test_collect_reports_no_progress_without_claiming_completion(self):
        self.r.d.dump_hierarchy=lambda:'<hierarchy>'+''.join(
            f'<node text="row {i}" bounds="[0,{50+i*20}][50,{65+i*20}]"/>' for i in range(3))+'</hierarchy>'
        self.r._call_original=self.r._call
        def call(name,args):
            if name=='swipe':return {'executed':True}
            return self.r._call_original(name,args)
        self.r._call=call
        result=self.r.call('android_collect_list',{'max_pages':3})
        self.assertEqual(result['pages_observed'],2)
        self.assertEqual(result['stop_reason'],'no_progress')
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['rows']),3)
    def test_cross_process_lock_blocks_and_releases(self):
        from android_lock import DeviceLock
        lock=DeviceLock('unit-test-no-real-phone')
        code="import sys;sys.path.insert(0,sys.argv[1]);from android_lock import DeviceLock\nwith DeviceLock('unit-test-no-real-phone').acquire():print('acquired')"
        def child():
            return subprocess.run([sys.executable,'-c',code,str(ROOT/'server')],capture_output=True,text=True,timeout=5)
        with lock.acquire():
            result=child()
            self.assertNotEqual(result.returncode,0)
            self.assertIn('device_busy',result.stderr)
        result=child()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('acquired',result.stdout)
    def test_disconnect_rejects_cached_connection_without_replay(self):
        runtime=m.Runtime('not-connected');runtime.d=Fake()
        with patch.object(m.adbutils.adb,'device_list',return_value=[]):
            with self.assertRaises(ConnectionError):runtime.connect()
        self.assertIsNone(runtime.d)
    def test_scrcpy_process_cannot_consume_mcp_input(self):
        import android_stream
        stream=android_stream.ScreenStream('fake')
        device=MagicMock()
        device.create_connection.return_value.recv.return_value=b''
        process=MagicMock();process.stdout=io.BytesIO(b'');process.poll.return_value=None
        with tempfile.TemporaryDirectory() as directory:
            jar=Path(directory)/'scrcpy-server';jar.write_bytes(b'fixture')
            environment={'ANDROID_USE_SCRCPY':'fake.exe','ANDROID_USE_SCRCPY_SERVER':str(jar),
                         'ANDROID_USE_SCRCPY_VERSION':'4.0','ANDROID_USE_ADB':'adb.exe'}
            with patch.dict(os.environ,environment),patch.object(android_stream.adbutils.adb,'device',return_value=device),patch.object(android_stream.subprocess,'Popen',return_value=process) as launch:
                with self.assertRaises(ConnectionError):stream.scrcpy()
                self.assertEqual(launch.call_args.kwargs['stdin'],subprocess.DEVNULL)
    def test_stdio_protocol_and_resource(self):
        messages = [{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}},
                    {'jsonrpc':'2.0','method':'notifications/initialized'},
                    {'jsonrpc':'2.0','id':2,'method':'tools/list'},
                    {'jsonrpc':'2.0','id':3,'method':'resources/read','params':{'uri':m.URI}}]
        p = subprocess.run([sys.executable, str(ROOT/'server/android_use.py')], input='\n'.join(map(json.dumps,messages))+'\n', capture_output=True, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(p.returncode, 0, p.stderr)
        replies = list(map(json.loads, p.stdout.splitlines()))
        self.assertEqual([r['id'] for r in replies], [1,2,3])
        self.assertEqual(len(replies[1]['result']['tools']), len(m.TOOLS))
        self.assertIn('android_screen_frame', replies[2]['result']['contents'][0]['text'])

if __name__ == '__main__': unittest.main()
