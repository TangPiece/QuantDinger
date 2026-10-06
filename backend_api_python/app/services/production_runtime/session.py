"""TradingSession + MarketSchedule（不把时钟写进策略）。"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from .protocol import RuntimeMarket, SessionPhase, TradingSession

_CN_TZ = ZoneInfo("Asia/Shanghai")
_HK_TZ = ZoneInfo("Asia/Hong_Kong")
_US_TZ = ZoneInfo("America/New_York")

# 市场 → (timezone, open, lunch_start, lunch_end, close) 本地时间
_SCHEDULE: dict[str, tuple[ZoneInfo, time, time | None, time | None, time]] = {
    "CN_A": (_CN_TZ, time(9, 30), time(11, 30), time(13, 0), time(15, 0)),
    "HK": (_HK_TZ, time(9, 30), time(12, 0), time(13, 0), time(16, 0)),
    "US": (_US_TZ, time(9, 30), None, None, time(16, 0)),
}

# market_schedule 用的 equity market 码
_MS_MARKET = {"CN_A": "CNStock", "HK": "HKStock", "US": "USStock"}


def _mins(t: time) -> int:
    return t.hour * 60 + t.minute


class MarketSchedule:
    """会话相位解析；CN 节假日尽力对齐 exchange_calendars / 本地时段表。"""

    def trading_date_for(self, market: RuntimeMarket | str, ts: datetime) -> date:
        tz = _SCHEDULE.get(str(market), _SCHEDULE["CN_A"])[0]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(tz).date()

    def phase_at(self, market: RuntimeMarket | str, ts: datetime) -> SessionPhase:
        """根据本地时钟返回会话相位（时段表在此封装，不进策略规则）。"""
        m = str(market)
        tz, t_open, lunch_s, lunch_e, t_close = _SCHEDULE.get(m, _SCHEDULE["CN_A"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        local = ts.astimezone(tz)
        cur = _mins(local.time())
        open_m = _mins(t_open)
        close_m = _mins(t_close)

        if cur < open_m:
            return "PRE_MARKET"
        # 开盘后 5 分钟
        if open_m <= cur < open_m + 5:
            return "MARKET_OPEN"
        # 收盘前 10 分钟
        if close_m - 10 <= cur < close_m:
            return "PRE_CLOSE"
        if close_m <= cur < close_m + 5:
            return "MARKET_CLOSE"
        if cur >= close_m + 5:
            return "POST_MARKET"
        # 午休仍属日内
        if lunch_s and lunch_e:
            if _mins(lunch_s) <= cur < _mins(lunch_e):
                return "INTRADAY"
        return "INTRADAY"

    def latest_session_date(
        self, market: RuntimeMarket | str, now: datetime | None = None
    ) -> date:
        """截至最新已完成交易日（尽力用 market_schedule）。"""
        now = now or datetime.now(timezone.utc)
        ms_key = _MS_MARKET.get(str(market), "CNStock")
        try:
            from app.services.market_schedule import latest_completed_session

            sess = latest_completed_session(ms_key, now, data_delay_minutes=15)
            if hasattr(sess, "date"):
                return sess.date()
            return date.fromisoformat(str(sess)[:10])
        except Exception:
            return self.trading_date_for(market, now)

    def build_session(
        self,
        market: RuntimeMarket | str,
        *,
        now: datetime | None = None,
        trading_date: date | None = None,
    ) -> TradingSession:
        now = now or datetime.now(timezone.utc)
        td = trading_date or self.trading_date_for(market, now)
        phase = self.phase_at(market, now)
        return TradingSession(
            market=market,  # type: ignore[arg-type]
            trading_date=td,
            phase=phase,
            as_of=now,
        )


def decision_bucket(phase: SessionPhase | str, now: datetime) -> str:
    """决策桶：日内按小时；开盘/收盘用相位名。"""
    if phase in (
        "MARKET_OPEN",
        "PRE_CLOSE",
        "MARKET_CLOSE",
        "PRE_MARKET",
        "POST_MARKET",
    ):
        return str(phase)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return f"INTRADAY_{now.astimezone(timezone.utc).strftime('%Y%m%d%H')}"
