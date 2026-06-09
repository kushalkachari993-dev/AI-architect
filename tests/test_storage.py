from app.services.architect import generate_architecture_package
from app.services.storage import list_projects, load_project, save_project


def test_storage_uses_configured_project_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_STORAGE_DIR", str(tmp_path / "projects"))
    package = generate_architecture_package("Inventory app", "As a user, I manage inventory.")

    metadata = save_project(package)

    assert metadata["persisted"] is True
    assert load_project(str(metadata["id"])) is not None
    assert list_projects()[0]["project_name"] == package.project_name


def test_storage_uses_postgres_when_database_url_is_configured(monkeypatch) -> None:
    package = generate_architecture_package("Inventory app", "As a user, I manage inventory.")
    calls = []

    monkeypatch.setenv("PRISMA_DATABASE_URL", "postgresql://example")
    monkeypatch.setattr("app.services.storage._save_project_postgres", lambda payload: calls.append(payload))

    metadata = save_project(package)

    assert metadata["persisted"] is True
    assert calls[0]["package"]["project_name"] == package.project_name
