#!/usr/bin/env python3
"""自动签到入口。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from checkin import CheckIn
from utils.balance_hash import load_balance_hash, save_balance_hash
from utils.config import AppConfig
from utils.notify import notify

load_dotenv(override=True)

BALANCE_HASH_FILE = "balance_hash.txt"
RESULT_FILE = Path("checkin-result.json")
CHINA_TIMEZONE = timezone(timedelta(hours=8))
SUCCESS_TASK_STATUSES = {"success", "already_done"}
PUBLIC_PROVIDER_NAMES = {"anyrouter", "huan666", "x666"}


def _failed_provider_result(provider: str, error_code: str) -> dict:
    """构造失败 Provider 的公开结果行。"""
    return {
        "provider": provider,
        "auth_status": "failed",
        "task_status": "failed",
        "error_code": error_code,
        "warnings": [],
    }


def generate_balance_hash(balances: dict) -> str:
    """生成不包含账号标识的余额变化哈希。"""
    simple_balances = {}
    for account_key, account_balances in balances.items():
        simple_balances[account_key] = [
            balance_info["quota"] for balance_info in account_balances.values()
        ]

    balance_json = json.dumps(simple_balances, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(balance_json.encode("utf-8")).hexdigest()[:16]


def _error_code(message: str | None) -> str | None:
    """把自由文本错误压缩成可公开的稳定错误码。"""
    if not message:
        return None

    normalized = message.lower()
    mappings = (
        ("no_valid_accounts", ("no valid accounts",)),
        ("auth_refresh_required", ("refresh storate_states_linuxdo", "session is expired")),
        ("authentication_failed", ("authentication", "oauth", "log-in", "login")),
        ("provider_task_failed", ("provider task", "spin failed", "topup failed", "failed to get cdk")),
        ("user_info_failed", ("user info",)),
        ("http_error", ("http ",)),
        ("invalid_response", ("invalid response", "response type")),
        ("timeout", ("timeout",)),
        ("configuration", ("configuration", "configured", "provider")),
    )
    for code, needles in mappings:
        if any(needle in normalized for needle in needles):
            return code

    return "unknown_error"


def _provider_result(
    provider: str,
    results: list[tuple[str, bool, dict | None]],
) -> tuple[dict, dict]:
    """汇总单个 Provider 的认证和业务任务结果。"""
    successful_methods = []
    failed_methods = []
    balances = {}
    successful_task_statuses = set()
    task_error_code = None
    authentication_error_code = None

    for auth_method, auth_succeeded, user_info in results:
        if auth_succeeded and user_info and user_info.get("success"):
            successful_methods.append(auth_method)
            method_task_status = user_info.get("task_status", "success")
            if method_task_status in SUCCESS_TASK_STATUSES:
                successful_task_statuses.add(method_task_status)
            else:
                task_error_code = _error_code(user_info.get("error")) or "provider_task_failed"
            balances[auth_method] = {
                "quota": user_info.get("quota", 0),
                "used": user_info.get("used_quota", 0),
                "bonus": user_info.get("bonus_quota", 0),
            }
        else:
            failed_methods.append(auth_method)
            authentication_error_code = (
                _error_code(user_info.get("error") if user_info else None) or "authentication_failed"
            )

    provider_success = bool(successful_task_statuses)
    task_status = "success" if "success" in successful_task_statuses else "already_done"
    error_code = None
    if not provider_success:
        task_status = "failed"
        error_code = task_error_code if successful_methods else authentication_error_code
        error_code = error_code or "no_authentication_result"
    result = {
        "provider": provider,
        "auth_status": "success" if successful_methods else "failed",
        "task_status": task_status if provider_success else "failed",
        "error_code": None if provider_success else error_code,
        "warnings": (
            ["some_authentication_methods_failed"]
            if successful_methods and failed_methods
            else []
        ),
    }
    return result, balances


def _render_summary(run_result: dict, notification_status: dict | None = None) -> str:
    """生成日志、邮件和 GitHub Job Summary 共用的 Markdown。"""
    status_label = "✅ 成功" if run_result["status"] == "success" else "❌ 失败"
    lines = [
        "# 自动签到结果",
        "",
        f"- 总体状态：{status_label}",
        f"- 执行时间：{run_result['generated_at']}",
        "",
        "| Provider | 认证 | 任务 | 错误码 |",
        "| --- | --- | --- | --- |",
    ]

    for provider in run_result["providers"]:
        lines.append(
            "| {provider} | {auth} | {task} | {error} |".format(
                provider=provider["provider"],
                auth=provider["auth_status"],
                task=provider["task_status"],
                error=provider["error_code"] or "-",
            )
        )

    if run_result["configuration_errors"]:
        lines.extend(["", "## 配置错误", ""])
        lines.extend(f"- `{_error_code(error) or 'configuration_error'}`" for error in run_result["configuration_errors"])

    if notification_status is not None:
        email_status = notification_status.get("Email", "not_configured")
        lines.extend(["", f"- 邮件通知：`{email_status}`"])

    return "\n".join(lines)


def _redact_run_result(run_result: dict) -> dict:
    """只保留可公开的运行结果字段。"""
    redacted_result = dict(run_result)
    redacted_result["required_providers"] = [
        provider if provider in PUBLIC_PROVIDER_NAMES else "custom_provider"
        for provider in run_result["required_providers"]
    ]
    redacted_result["providers"] = [
        {
            **provider_result,
            "provider": (
                provider_result["provider"]
                if provider_result["provider"] in PUBLIC_PROVIDER_NAMES
                else "custom_provider"
            ),
        }
        for provider_result in run_result["providers"]
    ]
    redacted_result["configuration_errors"] = [
        _error_code(error) or "configuration_error"
        for error in run_result["configuration_errors"]
    ]
    return redacted_result


def _write_outputs(run_result: dict, notification_status: dict | None = None) -> None:
    redacted_result = _redact_run_result(run_result)
    RESULT_FILE.write_text(
        json.dumps(redacted_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = _render_summary(redacted_result, notification_status)
    print(summary)

    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary_file:
            summary_file.write(summary)
            summary_file.write("\n")


async def main() -> int:
    """运行签到流程；所有必需 Provider 成功时返回 0。"""
    generated_at = datetime.now(CHINA_TIMEZONE).isoformat(timespec="seconds")
    print("🚀 newapi.ai multi-account auto check-in script started")
    print(f"🕒 Execution time: {generated_at}")

    app_config = AppConfig.load_from_env()
    print(f"⚙️ Loaded {len(app_config.providers)} provider(s)")
    print(f"⚙️ Found {len(app_config.accounts)} account(s)")

    run_result = {
        "status": "failed",
        "generated_at": generated_at,
        "required_providers": app_config.required_providers,
        "providers": [
            _failed_provider_result(provider, "configuration_error")
            for provider in app_config.required_providers
        ],
        "configuration_errors": list(app_config.configuration_errors),
    }

    if not app_config.accounts:
        run_result["configuration_errors"].append("No valid accounts were loaded")

    if run_result["configuration_errors"]:
        notification_payload = _redact_run_result(run_result)
        notification_status = notify.push_message(
            "Check-in failed",
            _render_summary(notification_payload),
            msg_type="text",
        )
        _write_outputs(run_result, notification_status)
        return 1

    last_balance_hash = load_balance_hash(BALANCE_HASH_FILE)
    current_balances = {}
    provider_results = {}

    for index, account_config in enumerate(app_config.accounts):
        account_name = account_config.get_display_name(index)
        provider_name = account_config.provider

        try:
            provider_config = app_config.get_provider(provider_name)
            if not provider_config:
                provider_result = _failed_provider_result(
                    provider_name,
                    "provider_not_configured",
                )
                balances = {}
            else:
                print(f"🌀 Processing {account_name} using provider '{provider_name}'")
                checkin = CheckIn(
                    account_name,
                    account_config,
                    provider_config,
                    global_proxy=app_config.global_proxy,
                )
                provider_result, balances = _provider_result(provider_name, await checkin.execute())
        except Exception as exc:
            print(f"❌ {provider_name}: processing exception: {type(exc).__name__}")
            provider_result = _failed_provider_result(
                provider_name,
                _error_code(type(exc).__name__) or "processing_exception",
            )
            balances = {}

        provider_results[provider_name] = provider_result
        if balances:
            current_balances[provider_name] = balances

    ordered_providers = app_config.required_providers or list(provider_results)
    run_result["providers"] = [
        provider_results.get(
            provider,
            _failed_provider_result(provider, "required_provider_missing"),
        )
        for provider in ordered_providers
    ]

    required_success = all(
        provider["task_status"] in SUCCESS_TASK_STATUSES
        for provider in run_result["providers"]
    )
    run_result["status"] = "success" if required_success else "failed"

    current_balance_hash = generate_balance_hash(current_balances) if current_balances else None
    balance_changed = current_balance_hash is not None and current_balance_hash != last_balance_hash
    if current_balance_hash:
        save_balance_hash(BALANCE_HASH_FILE, current_balance_hash)

    should_notify = not required_success or balance_changed or last_balance_hash is None
    notification_status = None
    if should_notify:
        email_subject = (
            "Check-in succeeded"
            if required_success
            else "Check-in failed"
        )
        notification_status = notify.push_message(
            email_subject,
            _render_summary(_redact_run_result(run_result)),
            msg_type="text",
        )

    _write_outputs(run_result, notification_status)
    return 0 if required_success else 1


def run_main() -> None:
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n⚠️ Program interrupted by user")
        sys.exit(1)
    except Exception as exc:
        print(f"\n❌ Program execution failed: {type(exc).__name__}")
        sys.exit(1)


if __name__ == "__main__":
    run_main()
