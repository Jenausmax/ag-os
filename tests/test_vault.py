from pathlib import Path

from core.vault import init_vault_structure, agent_raw_dir, wiki_dir, STANDARD_DIRS


def test_init_creates_all_standard_dirs(tmp_path):
    base = init_vault_structure(str(tmp_path / "vault"), git_enabled=False)
    for rel in STANDARD_DIRS:
        assert (base / rel).is_dir(), f"missing {rel}"


def test_init_creates_per_agent_raw_dirs(tmp_path):
    base = init_vault_structure(
        str(tmp_path / "v"),
        agent_names=["master", "researcher", "coder"],
        git_enabled=False,
    )
    assert (base / "raw" / "master").is_dir()
    assert (base / "raw" / "researcher").is_dir()
    assert (base / "raw" / "coder").is_dir()


def test_init_is_idempotent(tmp_path):
    base_path = str(tmp_path / "v")
    init_vault_structure(base_path, agent_names=["jira"], git_enabled=False)
    existing_file = Path(base_path) / "raw" / "jira" / "note.md"
    existing_file.write_text("existing content")
    init_vault_structure(base_path, agent_names=["jira", "new"], git_enabled=False)
    assert existing_file.read_text() == "existing content"
    assert (Path(base_path) / "raw" / "new").is_dir()


def test_agent_raw_dir_path(tmp_path):
    p = agent_raw_dir(str(tmp_path), "researcher")
    assert p == tmp_path / "raw" / "researcher"


def test_wiki_dir_path(tmp_path):
    p = wiki_dir(str(tmp_path))
    assert p == tmp_path / "wiki"


def test_git_init_optional(tmp_path, monkeypatch):
    # Когда git не найден — не крашится, просто warning
    import core.vault as vault_mod
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("git not installed")
    monkeypatch.setattr(vault_mod.subprocess, "run", fake_run)
    base = init_vault_structure(str(tmp_path / "v"), git_enabled=True)
    assert base.is_dir()
    assert not (base / ".git").exists()
