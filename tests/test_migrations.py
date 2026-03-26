"""マイグレーションの整合性テスト。

SQLite (aiosqlite) を使い、upgrade/downgrade が正しく動作することを確認する。
alembic/env.py は settings.DATABASE_URL を参照するため、
環境変数で SQLite パスを渡す。
"""
import os

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command

pytestmark = pytest.mark.no_db


def _alembic_cfg(db_path: str) -> Config:
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    # env.py は settings.DATABASE_URL を使うため環境変数経由で渡す
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    return cfg


def _sync_engine(db_path: str):
    return create_engine(f"sqlite:///{db_path}")


@pytest.fixture()
def db_path(tmp_path):
    path = str(tmp_path / "migration_test.db")
    yield path
    # 環境変数をクリア
    os.environ.pop("DATABASE_URL", None)


class TestMigrations:
    def test_upgrade_head_creates_all_tables(self, db_path):
        """upgrade head で全テーブルが作成される。"""
        command.upgrade(_alembic_cfg(db_path), "head")

        engine = _sync_engine(db_path)
        tables = inspect(engine).get_table_names()
        engine.dispose()

        for expected in [
            "users",
            "registered_apps",
            "miauth_sessions",
            "oauth_tokens",
            "mastodon_apps",
            "mastodon_oauth_states",
            "api_keys",
        ]:
            assert expected in tables, f"テーブル '{expected}' が存在しない"

    def test_upgrade_head_creates_user_limit_columns(self, db_path):
        """0003 マイグレーションで limit_max_tl / limit_max_notifications が追加される。"""
        command.upgrade(_alembic_cfg(db_path), "head")

        engine = _sync_engine(db_path)
        columns = {c["name"] for c in inspect(engine).get_columns("users")}
        engine.dispose()

        assert "limit_max_tl" in columns
        assert "limit_max_notifications" in columns

    def test_downgrade_base_removes_all_tables(self, db_path):
        """downgrade base で全テーブルが削除される。"""
        cfg = _alembic_cfg(db_path)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")

        engine = _sync_engine(db_path)
        tables = [t for t in inspect(engine).get_table_names() if t != "alembic_version"]
        engine.dispose()

        assert tables == []

    def test_up_down_up_cycle(self, db_path):
        """upgrade → downgrade → upgrade の往復が成功する。"""
        cfg = _alembic_cfg(db_path)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")

        engine = _sync_engine(db_path)
        tables = inspect(engine).get_table_names()
        engine.dispose()

        assert "users" in tables

    def test_each_revision_is_reachable(self, db_path):
        """各リビジョンを順番に適用でき、最終的に 0003 になる。"""
        cfg = _alembic_cfg(db_path)
        for rev in ["0001", "0002", "0003"]:
            command.upgrade(cfg, rev)

        engine = _sync_engine(db_path)
        with engine.connect() as conn:
            version = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
        engine.dispose()

        assert version == "0003"
