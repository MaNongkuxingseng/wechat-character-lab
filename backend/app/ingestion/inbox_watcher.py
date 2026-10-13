from pathlib import Path


class InboxWatcher:
    """只发现 Inbox 中待处理的 ZIP 文件，不负责读取或解析归档内容。"""

    def __init__(self, inbox_path: Path) -> None:
        self._inbox_path = inbox_path

    def discover_archives(self) -> list[Path]:
        """列出 Inbox 根目录下的 ZIP 文件；目录不存在时返回空列表。"""
        if not self._inbox_path.is_dir():
            return []
        return sorted(
            (
                path
                for path in self._inbox_path.iterdir()
                if path.is_file() and path.suffix.lower() == ".zip"
            ),
            key=lambda path: path.name.casefold(),
        )
