import asyncio
import json
from unittest.mock import patch

import pytest

import main
from utils.config import AccountConfig, ProviderConfig


def test_provider_accepts_already_done_after_other_authentication_failure():
	provider_result, balances = main._provider_result(
		'anyrouter',
		[
			('cookies', False, {'error': 'Session is expired'}),
			(
				'linux.do',
				True,
				{
					'success': True,
					'task_status': 'already_done',
					'quota': 100,
					'used_quota': 20,
					'bonus_quota': 5,
				},
			),
		],
	)

	assert provider_result == {
		'provider': 'anyrouter',
		'auth_status': 'success',
		'task_status': 'already_done',
		'error_code': None,
		'warnings': ['some_authentication_methods_failed'],
	}
	assert balances['linux.do']['quota'] == 100


@pytest.mark.parametrize(
	('results', 'expected_status'),
	[
		(
			[
				('linux.do', True, {'success': True, 'task_status': 'success'}),
				('github', True, {'success': True, 'task_status': 'already_done'}),
			],
			'success',
		),
		(
			[
				('linux.do', True, {'success': True, 'task_status': 'already_done'}),
				('github', True, {'success': True, 'task_status': 'success'}),
			],
			'success',
		),
	],
)
def test_provider_task_status_is_order_independent(results, expected_status):
	provider_result, _ = main._provider_result('anyrouter', results)

	assert provider_result['task_status'] == expected_status
	assert provider_result['error_code'] is None


@pytest.mark.parametrize(
	('task_status', 'error_code'),
	[
		('failed', 'provider_task_failed'),
		('pending', 'provider_task_failed'),
	],
)
def test_provider_task_failure_is_not_hidden_by_successful_authentication(task_status, error_code):
	provider_result, _ = main._provider_result(
		'x666',
		[
			(
				'linux.do',
				True,
				{'success': True, 'task_status': task_status, 'error': 'spin failed'},
			)
		],
	)

	assert provider_result['auth_status'] == 'success'
	assert provider_result['task_status'] == 'failed'
	assert provider_result['error_code'] == error_code


def test_summary_contains_public_error_codes_only():
	run_result = {
		'status': 'failed',
		'generated_at': '2026-08-06T12:00:00+08:00',
		'required_providers': ['anyrouter'],
		'providers': [
			{
				'provider': 'anyrouter',
				'auth_status': 'failed',
				'task_status': 'failed',
				'error_code': 'auth_refresh_required',
				'warnings': [],
			}
		],
		'configuration_errors': [
			'secret-cookie user-123 smtp-password must never appear in output',
		],
	}

	summary = main._render_summary(run_result)

	assert 'auth_refresh_required' in summary
	assert 'unknown_error' in summary
	assert 'secret-cookie' not in summary
	assert 'secret_cookie' not in summary
	assert 'user-123' not in summary
	assert 'user_123' not in summary
	assert 'smtp-password' not in summary
	assert 'smtp_password' not in summary


def test_redacted_result_hides_unknown_provider_names():
	run_result = {
		'status': 'failed',
		'generated_at': '2026-08-06T12:00:00+08:00',
		'required_providers': ['secret-token-provider'],
		'providers': [
			{
				'provider': 'secret-token-provider',
				'auth_status': 'failed',
				'task_status': 'failed',
				'error_code': 'unknown_error',
				'warnings': [],
			}
		],
		'configuration_errors': [],
	}

	redacted_result = main._redact_run_result(run_result)

	assert redacted_result['required_providers'] == ['custom_provider']
	assert redacted_result['providers'][0]['provider'] == 'custom_provider'


def test_main_fails_when_any_required_provider_task_fails(tmp_path, monkeypatch):
	required_providers = ['anyrouter', 'huan666', 'x666']
	configuration = main.AppConfig(
		providers={
			name: ProviderConfig(name=name, origin='https://example.test')
			for name in required_providers
		},
		accounts=[AccountConfig(provider=name, name=name) for name in required_providers],
		required_providers=required_providers,
	)

	class FakeCheckIn:
		def __init__(self, account_name, account_config, provider_config, global_proxy=None):
			self.account_name = account_name

		async def execute(self):
			task_status = 'failed' if self.account_name == 'x666' else 'already_done'
			return [
				(
					'linux.do',
					True,
					{
						'success': True,
						'task_status': task_status,
						'quota': 100,
						'used_quota': 10,
						'bonus_quota': 0,
						'error': 'spin failed' if task_status == 'failed' else '',
					},
				)
			]

	result_path = tmp_path / 'checkin-result.json'
	monkeypatch.setattr(main.AppConfig, 'load_from_env', lambda: configuration)
	monkeypatch.setattr(main, 'CheckIn', FakeCheckIn)
	monkeypatch.setattr(main, 'RESULT_FILE', result_path)
	monkeypatch.setattr(main, 'load_balance_hash', lambda _: 'existing-hash')
	monkeypatch.setattr(main, 'save_balance_hash', lambda *_: None)

	with patch.object(main.notify, 'push_message', return_value={'Email': 'not_configured'}):
		exit_code = asyncio.run(main.main())

	written_result = json.loads(result_path.read_text(encoding='utf-8'))
	assert exit_code == 1
	assert written_result['status'] == 'failed'
	assert [provider['task_status'] for provider in written_result['providers']] == [
		'already_done',
		'already_done',
		'failed',
	]
	assert written_result['providers'][-1]['error_code'] == 'provider_task_failed'


def test_configuration_failure_writes_result_and_attempts_notification(tmp_path, monkeypatch):
	configuration = main.AppConfig(
		providers={},
		accounts=[],
		required_providers=['anyrouter', 'huan666', 'x666'],
		configuration_errors=['Required provider account is missing: anyrouter'],
	)
	result_path = tmp_path / 'checkin-result.json'
	monkeypatch.setattr(main.AppConfig, 'load_from_env', lambda: configuration)
	monkeypatch.setattr(main, 'RESULT_FILE', result_path)

	with patch.object(main.notify, 'push_message', return_value={'Email': 'sent'}) as push_message:
		exit_code = asyncio.run(main.main())

	assert exit_code == 1
	push_message.assert_called_once()
	written_result = json.loads(result_path.read_text(encoding='utf-8'))
	assert written_result['status'] == 'failed'
	assert written_result['configuration_errors'] == [
		'configuration',
		'no_valid_accounts',
	]
	assert [
		(provider['provider'], provider['task_status'], provider['error_code'])
		for provider in written_result['providers']
	] == [
		('anyrouter', 'failed', 'configuration_error'),
		('huan666', 'failed', 'configuration_error'),
		('x666', 'failed', 'configuration_error'),
	]
