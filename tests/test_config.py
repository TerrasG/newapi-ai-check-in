import json
import os

import pytest

from utils.config import AppConfig


@pytest.fixture(autouse=True)
def clear_config_environment(monkeypatch):
	for name in (
		'ACCOUNTS',
		'ACCOUNTS_LINUX_DO',
		'ACCOUNTS_GITHUB',
		'PROVIDERS',
		'PROXY',
		'REQUIRED_PROVIDERS',
		'AUTO_ADD_REQUIRED_PROVIDERS',
	):
		monkeypatch.delenv(name, raising=False)


def _set_json_env(monkeypatch, name, payload):
	monkeypatch.setenv(name, json.dumps(payload))


def test_missing_anyrouter_is_auto_added_without_mutating_accounts_env(monkeypatch):
	accounts = [
		{'provider': 'huan666', 'linux.do': True},
		{'provider': 'x666', 'linux.do': True},
	]
	accounts_env = json.dumps(accounts)
	monkeypatch.setenv('ACCOUNTS', accounts_env)
	_set_json_env(monkeypatch, 'ACCOUNTS_LINUX_DO', [{'username': 'linuxdo-user', 'password': 'secret'}])
	monkeypatch.setenv('REQUIRED_PROVIDERS', 'anyrouter,huan666,x666')
	monkeypatch.setenv('AUTO_ADD_REQUIRED_PROVIDERS', 'anyrouter')

	config = AppConfig.load_from_env()

	assert config.configuration_errors == []
	assert [account.provider for account in config.accounts] == ['huan666', 'x666', 'anyrouter']
	assert config.accounts[-1].linux_do == config.linux_do_accounts
	assert config.accounts[-1].linux_do is not config.linux_do_accounts
	assert accounts == [
		{'provider': 'huan666', 'linux.do': True},
		{'provider': 'x666', 'linux.do': True},
	]
	assert os.environ['ACCOUNTS'] == accounts_env


@pytest.mark.parametrize(
	('env_updates', 'expected_error'),
	[
		(
			{
				'ACCOUNTS': [{'provider': 'huan666', 'linux.do': True}],
				'REQUIRED_PROVIDERS': 'huan666',
			},
			'Required provider account is missing: huan666',
		),
		(
			{
				'ACCOUNTS': [{'provider': 'not-configured', 'cookies': 'session', 'api_user': '1'}],
				'REQUIRED_PROVIDERS': '',
			},
			'Unknown provider in ACCOUNTS: not-configured',
		),
		(
			{
				'ACCOUNTS': [
					{'provider': 'anyrouter', 'cookies': 'session-1', 'api_user': '1'},
					{'provider': 'anyrouter', 'cookies': 'session-2', 'api_user': '2'},
				],
				'REQUIRED_PROVIDERS': 'anyrouter',
			},
			'Required provider has duplicate accounts: anyrouter',
		),
		(
			{
				'ACCOUNTS': [],
				'REQUIRED_PROVIDERS': 'unknown-target',
			},
			'Required provider is not configured: unknown-target',
		),
	],
)
def test_invalid_required_provider_configuration_is_reported(
	monkeypatch,
	env_updates,
	expected_error,
):
	for name, value in env_updates.items():
		if isinstance(value, list):
			_set_json_env(monkeypatch, name, value)
		else:
			monkeypatch.setenv(name, value)

	config = AppConfig.load_from_env()

	assert expected_error in config.configuration_errors


def test_auto_add_without_global_credentials_is_reported(monkeypatch):
	_set_json_env(monkeypatch, 'ACCOUNTS', [])
	monkeypatch.setenv('REQUIRED_PROVIDERS', 'anyrouter')
	monkeypatch.setenv('AUTO_ADD_REQUIRED_PROVIDERS', 'anyrouter')
	monkeypatch.delenv('ACCOUNTS_LINUX_DO', raising=False)
	monkeypatch.delenv('ACCOUNTS_GITHUB', raising=False)

	config = AppConfig.load_from_env()

	assert config.accounts == []
	assert config.configuration_errors == [
		'Auto-added provider has no usable global OAuth account: anyrouter'
	]


def test_duplicate_required_provider_names_are_rejected(monkeypatch):
	_set_json_env(monkeypatch, 'ACCOUNTS', [])
	monkeypatch.setenv('REQUIRED_PROVIDERS', 'anyrouter,ANYROUTER')

	config = AppConfig.load_from_env()

	assert 'Duplicate providers in REQUIRED_PROVIDERS: anyrouter' in config.configuration_errors


def test_invalid_duplicate_required_account_is_not_silently_discarded(monkeypatch):
	_set_json_env(
		monkeypatch,
		'ACCOUNTS',
		[
			{'provider': 'anyrouter', 'cookies': 'session', 'api_user': '1'},
			{'provider': 'anyrouter', 'linux.do': {'username': 'missing-password'}},
		],
	)
	monkeypatch.setenv('REQUIRED_PROVIDERS', 'anyrouter')

	config = AppConfig.load_from_env()

	assert 'Required provider has duplicate accounts: anyrouter' in config.configuration_errors
	assert 'Required provider account has invalid credentials: anyrouter' in config.configuration_errors
