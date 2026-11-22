import asyncio
import socket
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import aiohttp
import agent


class FakeRelay:
    def __init__(self, *args, on_status, **kwargs):
        self.on_status = on_status

    async def run(self):
        self.on_status('PC ready')
        await asyncio.Event().wait()


class DashboardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.args = SimpleNamespace(port=self.port, no_browser=True, dry_run=True, verbose=False)
        self.base = f'http://127.0.0.1:{self.port}'
        self.task = None
        self.client = aiohttp.ClientSession()

    async def asyncTearDown(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        await self.client.close()

    async def start(self):
        self.task = asyncio.create_task(agent.run_relay_dashboard(
            self.args, 'K7M2QX9P', 'https://example.com', 'key', 'https://example.com'))
        for _ in range(100):
            try:
                async with self.client.get(self.base + '/status') as response:
                    return await response.json()
            except aiohttp.ClientConnectorError:
                await asyncio.sleep(.01)
        self.fail('dashboard did not start')

    async def test_pairing_and_qr_no_browser(self):
        with patch.object(agent, 'Relay', FakeRelay), patch.object(agent.webbrowser, 'open') as browser:
            state = await self.start()
            self.assertEqual(state['room'], 'K7M2QX9P')
            self.assertEqual(state['phoneUrl'], 'https://example.com/#K7M2QX9P')
            self.assertEqual(state['status'], 'PC ready')
            browser.assert_not_called()
            async with self.client.get(self.base + '/host') as res:
                self.assertIn('PC dashboard', await res.text())
                self.assertEqual(res.headers['Cache-Control'], 'no-store')
            async with self.client.get(self.base + '/qr.svg') as res:
                self.assertEqual(res.status, 200)
                self.assertEqual(res.content_type, 'image/svg+xml')
                self.assertIn('<svg', await res.text())
            async with self.client.get(self.base + '/status', headers={'Host': 'attacker.example'}) as res:
                self.assertEqual(res.status, 403)

    async def test_settings_api_and_origin_protection(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(agent, 'ROOT', Path(folder)), patch.object(agent, 'Relay', FakeRelay):
            await self.start()
            async with self.client.get(self.base + '/settings') as res:
                settings = await res.json()
                self.assertEqual(settings['mode'], 'keyboard')
                self.assertEqual(settings['mappings']['cross'], 'space')
            payload = {'mode': 'keyboard', 'mappings': {'cross': 'x'}}
            async with self.client.post(self.base + '/settings', json=payload,
                                       headers={'Origin':'https://attacker.example'}) as res:
                self.assertEqual(res.status, 403)
            async with self.client.post(self.base + '/settings', json=payload,
                                       headers={'Origin': self.base}) as res:
                self.assertEqual(res.status, 200)
            self.assertTrue((Path(folder) / 'settings.json').exists())
            async with self.client.post(self.base + '/settings', json={'mode': 'bad'}) as res:
                self.assertEqual(res.status, 400)

    async def test_missing_driver_keeps_code_visible(self):
        with patch.object(agent, 'Output', side_effect=RuntimeError('driver missing')):
            state = await self.start()
            self.assertIn('FAILED', state['status'])
            self.assertEqual(state['room'], 'K7M2QX9P')
            self.assertFalse(self.task.done())

    async def test_browser_opens_host_not_controller(self):
        self.args.no_browser = False
        with patch.object(agent, 'Relay', FakeRelay), patch.object(agent.webbrowser, 'open') as browser:
            await self.start()
            browser.assert_called_once_with(self.base + '/host')

    async def test_second_agent_does_not_create_another_pad(self):
        with patch.object(agent, 'Relay', FakeRelay):
            await self.start()
            with patch.object(agent, 'Output') as pad:
                await agent.run_relay_dashboard(self.args, 'ABCDEFGH', '', '', '')
                pad.assert_not_called()


if __name__ == '__main__':
    unittest.main()
