"""008_close_delete_guard.sql 静态断言：服务端删除护栏关键子串。

纯文件读取（无 DB 依赖）。护栏语义：close 事件超 7 天禁止 DELETE
（历史事实保护，删除会使已平仓交易在复盘中复活）；前端 TradesLog 同口径禁用。
"""

from pathlib import Path

SQL_PATH = Path(__file__).resolve().parents[1] / "migrations" / "008_close_delete_guard.sql"


def _sql() -> str:
    return SQL_PATH.read_text(encoding="utf-8")


class TestCloseDeleteGuard:
    def test_before_delete_trigger_idempotent(self) -> None:
        sql = _sql()
        assert "DROP TRIGGER IF EXISTS trg_trades_close_delete_guard ON trades" in sql
        assert "BEFORE DELETE ON trades" in sql
        assert "EXECUTE FUNCTION enforce_close_delete_guard()" in sql

    def test_only_close_side_and_window(self) -> None:
        sql = _sql()
        assert "OLD.side = 'close'" in sql
        assert "- 7" in sql  # 7 天窗口

    def test_raises_with_error_code(self) -> None:
        sql = _sql()
        assert "RAISE EXCEPTION 'CLOSE_EVENT_LOCKED" in sql
        assert "USING ERRCODE = 'check_violation'" in sql

    def test_security_definer(self) -> None:
        assert "SECURITY DEFINER" in _sql()
