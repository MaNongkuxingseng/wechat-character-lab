"""运行 Alembic 数据库迁移，初始化本地 SQLite 数据库。"""

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

backend_dir = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(backend_dir))
config = Config(str(backend_dir / "alembic.ini"))
command.upgrade(config, "head")
