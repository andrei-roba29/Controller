"""Exercise the real agent websocket reader/writer with a local Phoenix peer."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import websockets
from agent import Relay, Session, VERSION
from keyboard_output import Output


class RelaySettingsTests(unittest.IsolatedAsyncioTestCase):
    async def test_settings_get_save_and_capability_over_websocket(self):
        replies = asyncio.Queue()
        peer = asyncio.get_running_loop().create_future()

        async def server(ws):
            join = json.loads(await ws.recv())
            await ws.send(json.dumps({'event':'phx_reply', 'ref':join['ref'],
                                      'payload':{'status':'ok'}}))
            peer.set_result(ws)
            try:
                async for raw in ws:
                    await replies.put(json.loads(raw))
            except websockets.exceptions.ConnectionClosed:
                pass  # The agent session is cancelled at test teardown.

        with tempfile.TemporaryDirectory() as folder:
            output = Output(Path(folder) / 'settings.json', dry_run=True)
            async with websockets.serve(server, '127.0.0.1', 0) as endpoint:
                port = endpoint.sockets[0].getsockname()[1]
                relay = Relay(f'http://127.0.0.1:{port}', 'test-key', 'K7M2QX9P', Session(output))
                with patch('agent.PC_ALIVE_EVERY', .02):
                    task = asyncio.create_task(relay._session())
                    try:
                        ws = await asyncio.wait_for(peer, 2)

                        async def exchange(request):
                            await ws.send(json.dumps({'event':'broadcast', 'payload':{
                                'event':'settings-request', 'payload':request}}))
                            while True:
                                reply = await asyncio.wait_for(replies.get(), 2)
                                if reply.get('payload', {}).get('event') == 'settings-response':
                                    return reply['payload']['payload']

                        read = await exchange({'id':'read1', 'action':'get'})
                        self.assertEqual(read['id'], 'read1')
                        self.assertEqual(read['mappings']['cross'], 'space')
                        saved = await exchange({'id':'write1', 'action':'save', 'settings':{
                            'mode':'keyboard', 'mappings':{'cross':'x','touchpad':'mouse_left'},
                            'rightStickMode':'mouse', 'mouseSpeed':1200, 'invertMouseY':True}})
                        self.assertEqual(saved['mappings']['cross'], 'x')
                        self.assertEqual(saved['mappings']['touchpad'], 'mouse_left')
                        self.assertEqual(saved['rightStickMode'], 'mouse')
                        self.assertEqual(saved['mouseSpeed'], 1200)
                        self.assertTrue(saved['invertMouseY'])
                        self.assertEqual(Output(output.path, dry_run=True).settings['mappings']['cross'], 'x')
                        while True:
                            frame = await asyncio.wait_for(replies.get(), 2)
                            if frame['payload']['event'] == 'pc-alive':
                                self.assertEqual(frame['payload']['payload']['agentVersion'], VERSION)
                                self.assertIn('settings-v1', frame['payload']['payload']['capabilities'])
                                break
                        output.error = 'test missing driver'
                        read = await exchange({'id':'error1', 'action':'get'})
                        self.assertEqual(read['outputError'], 'test missing driver')
                    finally:
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
