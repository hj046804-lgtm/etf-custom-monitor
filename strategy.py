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
    prior_close = c.shift(1)
    tr = pd.concat([(d['High']-d['Low']).abs(), (d['High']-prior_close).abs(), (d['Low']-prior_close).abs()], axis=1).max(axis=1)
    d['ATR14'] = tr.rolling(14).mean()
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
        vix_recent_fear = bool((vix['Close'].tail(10) >= 20).any())
        vix_falling = bool(vix['Close'].iloc[-1] < vix['Close'].iloc[-2])
        yield_value = float(tnx['Close'].iloc[-1])
        yield_avg = float(tnx['Close'].iloc[-11:-1].mean())
        spy_close = float(spy['Close'].iloc[-1])
        spy_ma200 = float(spy['Close'].rolling(200).mean().iloc[-1])
        spy_trend_ok = spy_close > spy_ma200
        market = {'spy_close': spy_close, 'spy_ma200': spy_ma200,
                  'spy_trend_ok': spy_trend_ok, 'spy_date': str(spy.index[-1].date()),
                  'vix': vix_value, 'yield': yield_value, 'yield_avg': yield_avg,
                  'vix_ok': vix_recent_fear and vix_falling, 'yield_ok': yield_value <= yield_avg,
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
            market_ok = True  # Market indicators are reference-only, not buy gates.
            signal = technical_count >= 3
            # Supplementary ATR-based five-session indicative range; not SigmaRange's proprietary model.
            atr = float(last['ATR14']) if pd.notna(last['ATR14']) else None
            band_half = atr * (5 ** 0.5) if atr is not None else None
            band_low = max(0.0, float(last['Close']) - band_half) if band_half is not None else None
            band_high = float(last['Close']) + band_half if band_half is not None else None
            # 20-session closing-price z-score (display only; does not affect buy alerts).
            # The current completed daily close is included in the 20-session window.
            recent_closes = d['Close'].tail(20)
            anchor = float(recent_closes.mean()) if len(recent_closes) == 20 else None
            sigma_unit = float(recent_closes.std(ddof=0)) if len(recent_closes) == 20 else None
            if sigma_unit is not None and not np.isfinite(sigma_unit):
                sigma_unit = None
            sigma_score = (float(last['Close']) - anchor) / sigma_unit if anchor is not None and sigma_unit is not None and sigma_unit > 0 else None
            high20 = float(d['High'].tail(20).max())
            low20 = float(d['Low'].tail(20).min())
            rows.append({'ticker': symbol, 'date': str(d.index[-1].date()),
                         'daily_change_pct': float((last['Close']/prev['Close']-1)*100) if prev['Close'] else None,
                         'range_low': band_low, 'range_high': band_high,
                         'range_width_pct': float(band_half/last['Close']*100) if band_half is not None and last['Close'] else None,
                         'range_position_pct': 50.0 if band_half is not None and band_half > 0 else None,
                         'sigma_anchor': anchor, 'sigma_unit': sigma_unit,
                         'sigma_score': sigma_score,
                         'sigma_lower': max(0.0, anchor-sigma_unit) if sigma_unit is not None else None,
                         'sigma_upper': anchor+sigma_unit if sigma_unit is not None else None,
                         'low20': low20, 'high20': high20,
                         'position20_pct': float((last['Close']-low20)/(high20-low20)*100) if high20>low20 else None,
                         'close': float(last['Close']), 'rsi': float(last['RSI']),
                         'volume_ratio': float(last['vol_ratio']) if pd.notna(last['vol_ratio']) else None,
                         'rsi_ok': rsi_ok, 'macd_ok': macd_ok, 'volume_ok': vol_ok,
                         'bb_ok': bb_ok, 'technical_count': technical_count,
                         'market_ok': market_ok, 'signal': signal})
        except Exception as exc:
            errors.append(f'{symbol}: {exc}')
    return rows, market, errors
