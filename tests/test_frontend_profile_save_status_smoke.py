from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_FILE = PROJECT_ROOT / "frontend" / "src" / "App.jsx"


def test_profile_save_status_copy_exists() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "BJTagent：本次型号尚未保存到本地库，可在确认后写入型号库" in source
    assert "BJTagent：已保存到本地型号库，后续可直接复用" in source


def test_profile_save_status_has_dedup_memory() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "unsavedProfileNoticeRef" in source
    assert "savedProfileNoticeRef" in source


def test_profile_save_status_uses_existing_context_sources() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "conversationState?.candidate_profile?.model" in source
    assert "conversationState?.pending_profile_model" in source
    assert "currentPlan?.model" in source
