import os

from app.config import load_dotenv


def test_load_dotenv_overrides_existing_values(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=from-file\n", encoding="utf-8")
    os.environ["OPENAI_API_KEY"] = "from-shell"

    load_dotenv(env_file)

    assert os.environ["OPENAI_API_KEY"] == "from-file"
