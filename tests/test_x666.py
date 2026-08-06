import asyncio
from types import SimpleNamespace

from utils import get_cdk
from utils.config import AccountConfig, OAuthAccountConfig


class _FakeCookies:
	def set(self, name, value):
		return None


class _FakeSession:
	def __init__(self, status_response):
		self.cookies = _FakeCookies()
		self.status_response = status_response
		self.post_called = False

	def get(self, *args, **kwargs):
		return self.status_response

	def post(self, *args, **kwargs):
		self.post_called = True
		raise AssertionError('spin must not run after already_done status')

	def close(self):
		return None


def test_x666_already_done_status_skips_spin(monkeypatch):
	session = _FakeSession(SimpleNamespace(status_code=200))
	monkeypatch.setattr(get_cdk.curl_requests, 'Session', lambda **kwargs: session)
	monkeypatch.setattr(
		get_cdk,
		'response_resolve',
		lambda response, operation, account_name: {
			'success': True,
			'can_spin': False,
			'today_record': {'quota_amount': 500},
		},
	)
	account = AccountConfig(
		provider='x666',
		name='x666',
		extra={'access_token': 'cached-token'},
	)

	async def collect_results():
		return [result async for result in get_cdk.get_x666_cdk(account)]

	results = asyncio.run(collect_results())

	assert results == [(True, {'code': '', 'task_status': 'already_done'})]
	assert session.post_called is False


def test_x666_missing_can_spin_field_is_a_failure(monkeypatch):
	session = _FakeSession(SimpleNamespace(status_code=200))
	monkeypatch.setattr(get_cdk.curl_requests, 'Session', lambda **kwargs: session)
	monkeypatch.setattr(
		get_cdk,
		'response_resolve',
		lambda response, operation, account_name: {'success': True},
	)
	account = AccountConfig(
		provider='x666',
		name='x666',
		extra={'access_token': 'cached-token'},
	)

	async def collect_results():
		return [result async for result in get_cdk.get_x666_cdk(account)]

	results = asyncio.run(collect_results())

	assert results == [(False, {'error': 'Invalid check-in status response'})]


def test_x666_expired_shared_session_is_reported_without_password_login(monkeypatch):
	calls = []

	async def fake_get_x666_user_token(account_name, username, proxy_config):
		calls.append((account_name, username, proxy_config))
		return None

	monkeypatch.setattr(get_cdk, '_get_x666_user_token', fake_get_x666_user_token)
	account = AccountConfig(
		provider='x666',
		name='x666',
		linux_do=[OAuthAccountConfig(username='linux-user', password='unused')],
	)

	async def collect_results():
		return [result async for result in get_cdk.get_x666_cdk(account)]

	results = asyncio.run(collect_results())

	assert calls == [('x666', 'linux-user', None)]
	assert results == [(False, {'error': 'Failed to obtain access_token via auto-login'})]
