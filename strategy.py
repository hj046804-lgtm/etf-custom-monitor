"""End-of-day ETF signal scanner. Informational alerts, not trading advice."""
from __future__ import annotations
import pandas as pd
import numpy as np
import yfinance as yf

ETFS = [
    'SPY','QQQ','DIA','IWM','VTI','VOO','IVV','SCHD','VIG','VYM',
    'XLK','XLF','XLV','XLE','XLI','XLP','XLY','XLU','XLB','XLRE',
    'SMH','SOXX','ARKK','IHI','IBB','XBI','EEM','EFA','GLD','SLV',
]
assert len(ETFS) == 30 and len(set(ETFS)) == 30 and 'TLT' not in ETFS

def prices(symbol: str, period='9mo') -> pd.DataFrame:
    df = yf.download(symbol, period=period, interval='1d', auto_adjust=True,
                     progress=False, threads=False)
    if df.empty:
        raise ValueError(f'{symbol}: 시세 데이터 없음')
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[['Open','Close','High','Low','Volume']].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None) if df.index.tz is not None else pd.to_datetime(df.index)
    return df.dropna(subset=['Close']).sort_index()

def latest_complete(df: pd.DataFrame, reference=None) -> pd.DataFrame:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = reference or datetime.now(ZoneInfo('America/New_York'))
    today = pd.Timestamp(now.date())
    if now.hour < 18:
        return df.loc[df.index.normalize() < today].copy()
    return df.loc[df.index.normalize() <= today].copy()

def indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    c = d['Close']
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rs = up / down.replace(0, np.nan)
    d['RSI'] = 100 - 100/(1+rs)
    d.loc[(down == 0) & (up > 0), 'RSI'] = 100
    d.loc[(down == 0) & (up == 0), 'RSI'] = 50
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    d['MACD'] = ema12 - ema26
    d['MACD_signal'] = d['MACD'].ewm(span=9, adjust=False).mean()
    d['golden'] = (d['MACD'] > d['MACD_signal']) & (d['MACD'].shift(1) <= d['MACD_signal'].shift(1))
    d['vol_avg20_prior'] = d['Volume'].shift(1).rolling(20).mean()
    d['vol_ratio'] = d['Volume'] / d['vol_avg20_prior'].replace(0, np.nan)
    ma20 = c.rolling(20).mean()
    std20 = c.rolling(20).std(ddof=0)
    d['BB_lower'] = ma20 - 2*std20
    return d

def scan(etfs=None) -> tuple[list[dict], dict, list[str]]:
    if etfs is None:
        etfs = []
    errors = []
    try:
        vix = latest_complete(prices('^VIX'))
        tnx = latest_complete(prices('^TNX'))
        spy = latest_complete(prices('SPY', period='18mo'))
        if len(vix) < 2 or len(tnx) < 11 or len(spy) < 200:
            raise ValueError('시장 데이터 부족')
        vix_value = float(vix['Close'].iloc[-1])
        yield_value = float(tnx['Close'].iloc[-1])
        yield_avg = float(tnx['Close'].iloc[-11:-1].mean())
        spy_close = float(spy['Close'].iloc[-1])
        spy_ma200 = float(spy['Close'].rolling(200).mean().iloc[-1])
        spy_trend_ok = spy_close > spy_ma200
        market = {'spy_close': spy_close, 'spy_ma200': spy_ma200,
                  'spy_trend_ok': spy_trend_ok, 'spy_date': str(spy.index[-1].date()),
                  'vix': vix_value, 'yield': yield_value, 'yield_avg': yield_avg,
                  'vix_ok': vix_value < 22, 'yield_ok': yield_value <= yield_avg,
                  'vix_date': str(vix.index[-1].date()), 'yield_date': str(tnx.index[-1].date())}
    except Exception as exc:
        return [], {}, [f'시장 지표 로드 실패: {exc}']

    rows = []
    for symbol in etfs:
        try:
            d = indicators(latest_complete(prices(symbol)))
            if len(d) < 35:
                raise ValueError('일봉 데이터 부족')
            last, prev = d.iloc[-1], d.iloc[-2]
            rsi_ok = bool(pd.notna(prev['RSI']) and pd.notna(last['RSI']) and prev['RSI'] <= 35 and last['RSI'] > prev['RSI'])
            macd_ok = bool(d['golden'].iloc[-2:].fillna(False).any())
            vol_ok = bool(pd.notna(last['vol_ratio']) and last['vol_ratio'] >= 1.20)
            bb_ok = bool(pd.notna(prev['BB_lower']) and pd.notna(last['BB_lower']) and prev['Close'] < prev['BB_lower'] and last['Close'] >= last['BB_lower'])
            technical_count = sum([rsi_ok, macd_ok, vol_ok, bb_ok])
            market_ok = market['spy_trend_ok'] and (market['vix_ok'] or market['yield_ok'])
            signal = market_ok and technical_count >= 3
            rows.append({'ticker': symbol, 'date': str(d.index[-1].date()),
                         'close': float(last['Close']), 'rsi': float(last['RSI']),
                         'volume_ratio': float(last['vol_ratio']) if pd.notna(last['vol_ratio']) else None,
                         'rsi_ok': rsi_ok, 'macd_ok': macd_ok, 'volume_ok': vol_ok,
                         'bb_ok': bb_ok, 'technical_count': technical_count,
                         'market_ok': market_ok, 'signal': signal})
        except Exception as exc:
            errors.append(f'{symbol}: {exc}')
    return rows, market, errors
