from __future__ import annotations

import json
from contextlib import contextmanager

from ai.test_planner import infer_goal, plan_from_text
from ai.transistor_db import lookup_transistor
from ai.assistant import build_execution_stats, local_execution_summary
from ai_cli import main


def test_lookup_known_transistor_profile() -> None:
    profile = lookup_transistor("s8050")

    assert profile.model == "S8050"
    assert profile.bjt_type == "NPN"
    assert profile.confidence == "catalog"


def test_plan_from_text_builds_safe_beta_plan() -> None:
    plan = plan_from_text("帮我测 S8050，重点看 beta")

    assert plan.model == "S8050"
    assert plan.goal == "beta"
    assert plan.bjt_type == "NPN"
    assert max(plan.vcc_steps) <= 5.0
    assert plan.ic_limit_a <= 0.03
    assert plan.power_limit_w <= 0.30
    assert plan.static_points


def test_unknown_model_uses_conservative_fallback() -> None:
    plan = plan_from_text("测 ABC9999，做完整报告")

    assert plan.model == "ABC9999"
    assert plan.bjt_type == "UNKNOWN"
    assert plan.profile["confidence"] == "fallback"
    assert max(plan.vcc_steps) <= 5.0
    assert any("未知型号" in note for note in plan.safety_notes)


def test_infer_goal_prefers_vce_sat_keywords() -> None:
    assert infer_goal("测 2N3904 的饱和压降和 beta") == "vce_sat"


def test_ai_cli_json_plan_without_api_key(monkeypatch, capsys) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("BJT_AI_MODE", raising=False)

    exit_code = main(["测", "S8050", "重点看", "beta", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["used_ai_api"] is False
    assert payload["used_openai_api"] is False
    assert payload["llm_provider"] == "local"
    assert payload["plan"]["model"] == "S8050"
    assert payload["execution"] is None


def test_ai_cli_executes_simulation_plan(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    exit_code = main(
        [
            "测",
            "S8050",
            "完整报告",
            "--execute",
            "--json",
            "--output-dir",
            str(tmp_path),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["execution"]["serial"] == "SIM-BJT-001"
    assert payload["execution"]["measurements"]
    assert len(payload["execution"]["measurements"]) == 1
    assert payload["execution_summary"]["summary"]
    assert (tmp_path / "ai_execution.json").exists()


def test_ai_cli_skips_pnp_auto_execution(monkeypatch, capsys) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    exit_code = main(["测", "S8550", "完整报告", "--execute", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["plan"]["bjt_type"] == "PNP"
    assert payload["execution"]["skipped"] is True


def test_ai_cli_requires_hardware_confirmation(monkeypatch, capsys) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    exit_code = main(
        [
            "测",
            "S8050",
            "重点看",
            "beta",
            "--mode",
            "hardware",
            "--execute",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["execution"]["skipped"] is True
    assert "显式允许" in payload["execution"]["reason"]


def test_ai_cli_hardware_confirmation_controls_execute_policy(monkeypatch, tmp_path, capsys) -> None:
    calls = {}

    def fake_execute_plan(plan, *, mode, output_dir=None, allow_hardware=False, token_valid=None):
        calls["mode"] = mode
        calls["output_dir"] = output_dir
        calls["allow_hardware"] = allow_hardware
        calls["token_valid"] = token_valid
        return {
            "plan": plan.to_dict(),
            "mode": mode,
            "serial": "HW-MOCK",
            "measurements": [],
        }

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr("ai_cli.execute_plan", fake_execute_plan)

    exit_code = main(
        [
            "测",
            "S8050",
            "重点看",
            "beta",
            "--mode",
            "hardware",
            "--execute",
            "--confirm-hardware",
            "--json",
            "--output-dir",
            str(tmp_path),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["execution"]["serial"] == "HW-MOCK"
    assert calls == {
        "mode": "hardware",
        "output_dir": tmp_path,
        "allow_hardware": True,
        "token_valid": True,
    }


def test_ai_cli_executes_all_beta_static_points_in_simulation(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    exit_code = main(
        [
            "测",
            "S8050",
            "重点看",
            "beta",
            "--execute",
            "--json",
            "--output-dir",
            str(tmp_path),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert len(payload["execution"]["measurements"]) == 6
    assert payload["execution"]["limits"]["power_limit_w"] == 0.0875
    assert payload["execution"]["execution_json"] == str(tmp_path / "ai_execution.json")
    assert "Beta" in payload["execution_summary"]["summary"]


def test_local_execution_summary_reports_beta_stats() -> None:
    result = {
        "measurements": [
            {"beta": 20.0, "region": "cutoff", "Ic": 0.001, "Vce": 2.5},
            {"beta": 40.0, "region": "active", "Ic": 0.002, "Vce": 2.3},
            {"beta": 60.0, "region": "active", "Ic": 0.003, "Vce": 2.1},
        ]
    }

    stats = build_execution_stats(result)
    summary = local_execution_summary(stats)

    assert stats["point_count"] == 3
    assert stats["active_beta_median"] == 50.0
    assert "Beta 范围 20.0 - 60.0" in summary


def test_ai_cli_uses_deepseek_when_configured(monkeypatch, capsys) -> None:
    calls = {}

    class FakeResponse:
        def read(self):
            return json.dumps(
                {
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 20,
                        "total_tokens": 120,
                    },
                    "choices": [
                        {
                            "message": {
                                "content": "DeepSeek 已根据安全计划生成说明。"
                            }
                        }
                    ]
                }
            ).encode("utf-8")

    @contextmanager
    def fake_urlopen(request, timeout):
        calls["url"] = request.full_url
        calls["timeout"] = timeout
        calls["body"] = json.loads(request.data.decode("utf-8"))
        yield FakeResponse()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("BJT_AI_MODE", "cloud")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    exit_code = main(["测", "S8050", "重点看", "beta", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["used_ai_api"] is True
    assert payload["used_openai_api"] is False
    assert payload["llm_provider"] == "deepseek:deepseek-v4-flash"
    assert payload["llm_usage"]["total_tokens"] == 120
    assert calls["url"] == "https://api.deepseek.com/chat/completions"
    assert calls["body"]["model"] == "deepseek-v4-flash"
    assert calls["body"]["messages"][0]["role"] == "system"
