import smtplib
from unittest.mock import MagicMock, patch

import pytest

from utils.notify import NotificationKit


@pytest.fixture(autouse=True)
def clear_notification_environment(monkeypatch):
	for name in (
		'EMAIL_USER',
		'EMAIL_PASS',
		'EMAIL_TO',
		'CUSTOM_SMTP_SERVER',
		'PUSHPLUS_TOKEN',
		'SERVERPUSHKEY',
		'DINGDING_WEBHOOK',
		'FEISHU_WEBHOOK',
		'WEIXIN_WEBHOOK',
		'TELEGRAM_BOT_TOKEN',
		'TELEGRAM_CHAT_ID',
	):
		monkeypatch.delenv(name, raising=False)


def test_send_email_uses_configured_smtp(monkeypatch):
	monkeypatch.setenv('EMAIL_USER', 'sender@example.com')
	monkeypatch.setenv('EMAIL_PASS', 'smtp-token')
	monkeypatch.setenv('EMAIL_TO', 'recipient@example.com')
	monkeypatch.setenv('CUSTOM_SMTP_SERVER', 'smtp.example.com')
	smtp_server = MagicMock()

	with patch('utils.notify.smtplib.SMTP_SSL', return_value=smtp_server):
		NotificationKit().send_email('subject', 'content')

	smtp_server.__enter__.return_value.login.assert_called_once_with(
		'sender@example.com',
		'smtp-token',
	)
	smtp_server.__enter__.return_value.send_message.assert_called_once()


def test_send_email_reports_missing_configuration(monkeypatch):
	monkeypatch.delenv('EMAIL_USER', raising=False)
	monkeypatch.delenv('EMAIL_PASS', raising=False)
	monkeypatch.delenv('EMAIL_TO', raising=False)

	try:
		NotificationKit().send_email('subject', 'content')
	except ValueError as error:
		assert str(error) == 'Email configuration not set'
	else:
		raise AssertionError('send_email must reject missing configuration')


def test_push_message_reports_channel_statuses(monkeypatch):
	monkeypatch.setenv('EMAIL_USER', 'sender@example.com')
	monkeypatch.setenv('EMAIL_PASS', 'smtp-token')
	monkeypatch.setenv('EMAIL_TO', 'recipient@example.com')

	with patch(
		'utils.notify.smtplib.SMTP_SSL',
		side_effect=smtplib.SMTPException('smtp unavailable'),
	):
		statuses = NotificationKit().push_message('subject', 'content')

	assert statuses['Email'] == 'failed'
	assert statuses['PushPlus'] == 'not_configured'
	assert statuses['Telegram'] == 'not_configured'


def test_push_message_marks_http_failure_as_failed(monkeypatch):
	monkeypatch.setenv('PUSHPLUS_TOKEN', 'push-token')
	response = MagicMock(status_code=500)

	with patch('utils.notify.curl_requests.post', return_value=response):
		statuses = NotificationKit().push_message('subject', 'content')

	assert statuses['PushPlus'] == 'failed'


def test_push_message_marks_non_json_http_response_as_failed(monkeypatch):
	monkeypatch.setenv('PUSHPLUS_TOKEN', 'push-token')
	response = MagicMock(status_code=200)
	response.json.side_effect = ValueError

	with patch('utils.notify.curl_requests.post', return_value=response):
		statuses = NotificationKit().push_message('subject', 'content')

	assert statuses['PushPlus'] == 'failed'


def test_push_message_marks_non_object_json_response_as_failed(monkeypatch):
	monkeypatch.setenv('PUSHPLUS_TOKEN', 'push-token')
	response = MagicMock(status_code=200)
	response.json.return_value = []

	with patch('utils.notify.curl_requests.post', return_value=response):
		statuses = NotificationKit().push_message('subject', 'content')

	assert statuses['PushPlus'] == 'failed'
