from typing import Literal, Optional

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class DiscoveryWeights(BaseModel):
    profit: float = 2.0
    efficiency: float = 15.0
    win_rate: float = 5.0


class DiscoveryConfig(BaseModel):
    min_sibling_count: int = 2
    min_cluster_score: Optional[float] = None
    funding_hops: int = 3
    profit_formula: Literal["sqrt", "log", "piecewise"] = "sqrt"
    subtract_losses: bool = False
    weights: DiscoveryWeights = DiscoveryWeights()
    efficiency_cap: float = 10.0
    min_exit_count_for_win_rate: int = 1


class EntryConfig(BaseModel):
    min_buy_usd: float = 500.0
    market_tags: list[str] = []
    max_odds_enabled: bool = True
    max_odds: float = 0.5
    mirror_pct: float = 1.0
    mirror_cap_usd: Optional[float] = None
    post_entry_poll_interval_sec: int = 10
    post_entry_poll_count: int = 6
    hedge_filter_mode: Literal["net_only", "filter_before_net"] = "net_only"
    ignore_hedge_trades: bool = True
    hedge_dominant_threshold: float = 2.0
    follow_reentry_after_sell: bool = True
    reentry_window_minutes: int = 5


class ExitConfig(BaseModel):
    poll_interval_sec: int = 60
    take_profit_enabled: bool = False
    take_profit_pct: float = 0.50
    stop_loss_enabled: bool = False
    stop_loss_pct: float = 0.25
    max_hold_hours: Optional[int] = None
    close_on_resolution: bool = True
    add_on_repeat_buy: bool = False
    notify_on_repeat_buy: bool = True
    resolution_source: Literal["data_api_isResolved"] = "data_api_isResolved"
    tp_sl_suspend_mirror_until_flat: bool = True
    max_slippage_pct: Optional[float] = None


class ReviewConfig(BaseModel):
    mode: Literal["all", "live_only", "none"] = "live_only"


class ExecutionConfig(BaseModel):
    mode: Literal["observe", "paper", "live"] = "paper"


class PaperConfig(BaseModel):
    fill_model: Literal["orderbook_walk_next_poll"] = "orderbook_walk_next_poll"
    pessimistic_slippage_pct: float = 0.0


class ConflictConfig(BaseModel):
    policy: Literal["alert_only", "net_cluster_position"] = "net_cluster_position"
    min_net_usd: float = 100.0
    dust_shares: float = 0.001
    always_alert: bool = True


class PositionConfig(BaseModel):
    signal_expire_minutes: Optional[int] = None
    market_watch_expire_days: Optional[int] = None


class WatchConfig(BaseModel):
    account_expire_days: Optional[int] = None


class AlertsConfig(BaseModel):
    channels: list[str] = ["dashboard"]


class RetentionConfig(BaseModel):
    raw_trades_days: int = 90
    analytics_indefinite: bool = True


class SessionsConfig(BaseModel):
    private_default: bool = False


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="POLY_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: Optional[str] = None
    rpc_url: Optional[str] = None

    discovery: DiscoveryConfig = DiscoveryConfig()
    entry: EntryConfig = EntryConfig()
    exit: ExitConfig = ExitConfig()
    review: ReviewConfig = ReviewConfig()
    execution: ExecutionConfig = ExecutionConfig()
    paper: PaperConfig = PaperConfig()
    conflict: ConflictConfig = ConflictConfig()
    position: PositionConfig = PositionConfig()
    watch: WatchConfig = WatchConfig()
    alerts: AlertsConfig = AlertsConfig()
    retention: RetentionConfig = RetentionConfig()
    sessions: SessionsConfig = SessionsConfig()
