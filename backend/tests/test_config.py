import os
from pathlib import Path
from app.core.config import Settings, _REPO_ROOT, _ROOT_ENV


def test_root_env_path_points_to_repo_root():
    """Verify _ROOT_ENV is located at the repository root."""
    assert _ROOT_ENV.parent == _REPO_ROOT
    assert _ROOT_ENV.name == ".env"


def test_settings_loads_from_root_or_backend_cwd(monkeypatch, tmp_path):
    """Verify Settings resolves root .env regardless of whether CWD is repo root or backend/."""
    fake_root = tmp_path / "repo_root"
    fake_backend = fake_root / "backend"
    fake_root.mkdir()
    fake_backend.mkdir()

    fake_root_env = fake_root / ".env"
    fake_root_env.write_text("SEARCH_PROVIDER=custom_from_root\n", encoding="utf-8")

    # Subclass with custom fake root env path
    class CustomSettings(Settings):
        model_config = {
            "env_file": (fake_root_env, ".env"),
            "env_file_encoding": "utf-8",
            "extra": "ignore",
        }

    # Case 1: CWD is fake_root
    monkeypatch.chdir(fake_root)
    s1 = CustomSettings()
    assert s1.SEARCH_PROVIDER == "custom_from_root"

    # Case 2: CWD is fake_backend
    monkeypatch.chdir(fake_backend)
    s2 = CustomSettings()
    assert s2.SEARCH_PROVIDER == "custom_from_root"
