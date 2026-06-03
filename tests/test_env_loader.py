from __future__ import annotations

import os

from ai.env_loader import load_dotenv


def test_load_dotenv_reads_local_keys_without_overriding_existing_env(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
# comment
TAVILY_API_KEY=tvly-test
DEEPSEEK_API_KEY="deepseek-test"
BJT_DATASHEET_LOOKUP=1 # inline comment
export BJT_AI_PROVIDER=deepseek
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("TAVILY_API_KEY", "already-set")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("BJT_DATASHEET_LOOKUP", raising=False)
    monkeypatch.delenv("BJT_AI_PROVIDER", raising=False)

    loaded = load_dotenv(env_file)

    assert "TAVILY_API_KEY" not in loaded
    assert os.environ["TAVILY_API_KEY"] == "already-set"
    assert loaded["DEEPSEEK_API_KEY"] == "deepseek-test"
    assert os.environ["BJT_DATASHEET_LOOKUP"] == "1"
    assert os.environ["BJT_AI_PROVIDER"] == "deepseek"


def test_load_dotenv_can_override_existing_env(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("TAVILY_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("TAVILY_API_KEY", "from-shell")

    loaded = load_dotenv(env_file, override=True)

    assert loaded["TAVILY_API_KEY"] == "from-file"
    assert os.environ["TAVILY_API_KEY"] == "from-file"
