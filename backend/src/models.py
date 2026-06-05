"""Pydantic 模型 — 与 JSON Schema 1:1 对应"""
from typing import Literal, Optional
from pydantic import BaseModel, Field

MatchType = Literal['exact', 'wide']
SignalType = Literal['resonance', 'transmission', 'divergence']
ProviderStatus = Literal['ok', 'degraded', 'stale']
DimName = Literal['short', 'mid', 'long']


class CnEtfConfig(BaseModel):
    code: str
    name: str
    tracking: str
    match_type: MatchType


class ThemeConfig(BaseModel):
    id: str
    name: str
    us_etfs: list[str]
    primary_us: str
    tags: list[str] = Field(default_factory=list)
    note: str = ''
    cn_etfs: list[CnEtfConfig]


class StrengthSubConfig(BaseModel):
    k_sigmoid: float
    threshold: float
    days_in_dim: dict[str, int]
    composite_weights: dict[str, float]


class MappingSubConfig(BaseModel):
    corr_window_days: int
    min_aligned_days: int


class ConfidenceSubConfig(BaseModel):
    exact: int
    wide: int


class SignalSubConfig(BaseModel):
    resonance: dict[str, float]
    transmission: dict[str, float]
    divergence: dict[str, float]


class AlgoConfig(BaseModel):
    strength: StrengthSubConfig
    mapping: MappingSubConfig
    confidence: ConfidenceSubConfig
    signal: SignalSubConfig


class Returns(BaseModel):
    r_1d: Optional[float] = None
    r_5d: Optional[float] = None
    r_20d: Optional[float] = None
    r_60d: Optional[float] = None
    r_120d: Optional[float] = None
    r_ytd: Optional[float] = None


class Strength(BaseModel):
    short: int = Field(ge=0, le=100)
    mid: int = Field(ge=0, le=100)
    long: int = Field(ge=0, le=100)
    composite: int = Field(ge=0, le=100)


class Rank(BaseModel):
    short: int
    mid: int
    long: int
    composite: int


class ThemeOutput(BaseModel):
    id: str
    name: str
    us_etfs: list[str]
    primary_us: str
    tags: list[str]
    note: str
    returns: Returns
    strength: Strength
    rank: Rank


class EtfOutput(BaseModel):
    code: str
    name: str
    tracking_index: str
    returns: Returns
    amount_yi: Optional[float] = None
    price: Optional[float] = None
    strength: Strength


class PairSignal(BaseModel):
    theme_id: str
    cn_code: str
    mapping_score: Optional[int]
    confidence: int
    signal: Optional[SignalType]
    votes: dict[str, Optional[SignalType]]


class ThemeSignal(BaseModel):
    theme_id: str
    signal: Optional[SignalType]
    trigger_cn_etf: Optional[str]
    votes: dict[str, Optional[SignalType]]
    description: str


class TopTheme(BaseModel):
    id: str
    name: str
    primary_us: str
    composite_strength: int


class SignalsSummary(BaseModel):
    themes_total: int
    etfs_total: int
    resonance_count: int
    transmission_count: int
    divergence_count: int
    top_theme: Optional[TopTheme]


class ProviderInfo(BaseModel):
    status: ProviderStatus
    name: str


class CalendarInfo(BaseModel):
    us_trading_today: bool
    cn_trading_today: bool
    us_session_active: bool
    cn_session_active: bool


class FullRefreshTimes(BaseModel):
    us: Optional[str] = None
    cn: Optional[str] = None


class MetaInfo(BaseModel):
    schema_version: str = '1.0'
    last_full_refresh: FullRefreshTimes
    last_intraday_refresh: Optional[str] = None
    providers: dict[str, ProviderInfo]
    failed_symbols: list[str] = Field(default_factory=list)
    stale_minutes: int = 0
    calendar: CalendarInfo
