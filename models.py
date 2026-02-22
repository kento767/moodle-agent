"""
課題（Assignment）のデータ構造。
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Assignment:
    """Moodle の課題 1 件を表す。"""

    title: str
    due_date: Optional[datetime]
    course_name: str
    url: str
    description_preview: str = ""

    def is_due_within_days(self, days: int) -> bool:
        """締切が今日から days 日以内なら True。"""
        if self.due_date is None:
            return False
        from datetime import date, timedelta
        today = date.today()
        end = today + timedelta(days=days)
        due_date = self.due_date.date() if hasattr(self.due_date, "date") else self.due_date
        return today <= due_date <= end

    def lesson_number(self) -> str:
        """タイトルから「第N回」を抽出。なければ空文字。"""
        import re
        m = re.search(r"第\s*(\d+)\s*回", self.title)
        return m.group(0) if m else ""

    def format_for_line(self, base_url: str) -> str:
        """LINE 用の 1 行〜数行テキストに整形。"""
        lines = [f"・{self.title}", f"  コース: {self.course_name}"]
        if self.due_date:
            lines.append(f"  締切: {self.due_date.strftime('%Y-%m-%d %H:%M')}")
        if self.url:
            # 相対 URL の場合はベースを付与
            url = self.url if self.url.startswith("http") else (base_url.rstrip("/") + "/" + self.url.lstrip("/"))
            lines.append(f"  {url}")
        if self.description_preview:
            preview = self.description_preview[:80].replace("\n", " ")
            if len(self.description_preview) > 80:
                preview += "..."
            lines.append(f"  {preview}")
        return "\n".join(lines)
