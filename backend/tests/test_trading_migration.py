"""006_trades.sql 静态断言：表结构 / RLS 策略边界 / 幂等写法关键子串。

纯文件读取（无 DB 依赖），照 migrations 003 惯例审查：
- trades / trading_settings：本人 FOR ALL（authenticated 读写）
- trade_reviews：仅本人 SELECT，无写策略（Actions service_role 写入）
"""

from pathlib import Path

SQL_PATH = Path(__file__).resolve().parents[1] / "migrations" / "006_trades.sql"


def _sql() -> str:
    return SQL_PATH.read_text(encoding="utf-8")


class TestTradesTable:
    def test_idempotent_create(self) -> None:
        assert "CREATE TABLE IF NOT EXISTS trades" in _sql()

    def test_side_check_constraint(self) -> None:
        assert "CHECK (side IN ('open','add','reduce','close'))" in _sql()

    def test_user_index(self) -> None:
        assert "CREATE INDEX IF NOT EXISTS idx_trades_user" in _sql()

    def test_updated_at_trigger(self) -> None:
        sql = _sql()
        assert "DROP TRIGGER IF EXISTS trg_trades_updated ON trades" in sql
        assert "EXECUTE FUNCTION set_updated_at()" in sql

    def test_rls_own_for_all(self) -> None:
        sql = _sql()
        assert "DROP POLICY IF EXISTS trades_own ON trades" in sql
        assert "CREATE POLICY trades_own ON trades" in sql
        assert "FOR ALL TO authenticated" in sql
        assert "USING      (user_id = auth.uid())" in sql
        assert "WITH CHECK (user_id = auth.uid())" in sql


class TestTradeReviewsTable:
    def test_idempotent_create(self) -> None:
        assert "CREATE TABLE IF NOT EXISTS trade_reviews" in _sql()

    def test_trade_fk(self) -> None:
        assert "REFERENCES trades(id) ON DELETE CASCADE" in _sql()

    def test_select_only_policy(self) -> None:
        """本人仅 SELECT；不允许 authenticated 写（无 FOR ALL/INSERT/UPDATE/DELETE 策略）。"""
        sql = _sql()
        assert "CREATE POLICY trade_reviews_own_select ON trade_reviews" in sql
        assert "FOR SELECT TO authenticated" in sql
        # trade_reviews 上只允许出现这一个策略（own_select），杜绝写策略混入
        policies_on_reviews = [
            line for line in sql.splitlines() if "ON trade_reviews" in line and "POLICY" in line
        ]
        assert policies_on_reviews == [
            "DROP POLICY IF EXISTS trade_reviews_own_select ON trade_reviews;",
            "CREATE POLICY trade_reviews_own_select ON trade_reviews",
        ]

    def test_no_rls_bypass_grant(self) -> None:
        """不应出现绕过 RLS 的 SECURITY DEFINER 函数（写路径归 Actions service_role）。"""
        assert "SECURITY DEFINER" not in _sql()


class TestTradingSettingsTable:
    def test_idempotent_create(self) -> None:
        assert "CREATE TABLE IF NOT EXISTS trading_settings" in _sql()

    def test_defaults_match_spec(self) -> None:
        """默认值 = 规格 §1 第 7 条：0.75% 单笔风险 / 5 只 / 20% 单票 / 4% 组合。"""
        sql = _sql()
        assert "risk_per_trade_pct     numeric     NOT NULL DEFAULT 0.75" in sql
        assert "max_positions          int         NOT NULL DEFAULT 5" in sql
        assert "max_position_pct       numeric     NOT NULL DEFAULT 20" in sql
        assert "max_portfolio_risk_pct numeric     NOT NULL DEFAULT 4" in sql

    def test_user_id_pk(self) -> None:
        assert "user_id                uuid        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE" in _sql()

    def test_rls_own_for_all(self) -> None:
        sql = _sql()
        assert "DROP POLICY IF EXISTS trading_settings_own ON trading_settings" in sql
        assert "CREATE POLICY trading_settings_own ON trading_settings" in sql


class TestCommonConventions:
    def test_rls_enabled_on_all_three(self) -> None:
        sql = _sql()
        assert "ALTER TABLE trades ENABLE ROW LEVEL SECURITY" in sql
        assert "ALTER TABLE trade_reviews ENABLE ROW LEVEL SECURITY" in sql
        assert "ALTER TABLE trading_settings ENABLE ROW LEVEL SECURITY" in sql

    def test_all_tables_reference_auth_users_cascade(self) -> None:
        assert _sql().count("REFERENCES auth.users(id) ON DELETE CASCADE") == 3
