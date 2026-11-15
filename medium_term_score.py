"""Medium-term ETF pullback score (6-12 months). Display-only, not an alert gate."""
import math
import numpy as np
import pandas as pd
import yfinance as yf
from strategy import prices, latest_complete, indicators

LEVERAGED = {"TQQQ","SQQQ","SOXL","SOXS","UPRO","SPXL","SPXS","TECL","TECS","TNA","TZA","FAS","FAZ","LABU","LABD","TMF","TBT","QLD","SSO"}

def _clip(x, low=0, high=1):
    return max(low, min(high, float(x)))

def _weekly_rsi(close):
    delta=close.diff()
    up=delta.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    down=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    result=100-100/(1+up/down.replace(0,np.nan))
    result= result.mask((down==0)&(up>0),100).mask((down==0)&(up==0),50)
    return result

def _get(symbol):
    return indicators(latest_complete(prices(symbol,period="3y")))

def score_one(symbol, spy):
    d=_get(symbol)
    if len(d)<260:
        raise ValueError("52주·200일선 계산을 위한 데이터 부족")
    c=d["Close"]
    price=float(c.iloc[-1])
    high52=float(d["High"].tail(252).max())
    dd=(price/high52-1)*100
    ma20=float(c.tail(20).mean())
    ma50=float(c.tail(50).mean())
    ma200=float(c.tail(200).mean())
    rsi=float(d["RSI"].iloc[-1])
    prev_rsi=float(d["RSI"].iloc[-2])
    vol_ratio=float(d["vol_ratio"].iloc[-1])
    macd_up=bool(d["MACD"].iloc[-1]>d["MACD_signal"].iloc[-1])
    # Resample completed daily closes to weekly observations, excluding incomplete current week.
    weekly=c.resample("W-FRI").last().dropna()
    from datetime import datetime
    from zoneinfo import ZoneInfo
    today=datetime.now(ZoneInfo("America/New_York")).date()
    weekly=weekly[weekly.index.date<=today]
    wr=_weekly_rsi(weekly)
    if len(wr)<35 or not np.isfinite(wr.iloc[-1]) or not np.isfinite(wr.iloc[-2]):
        raise ValueError("주봉 RSI 데이터 부족")
    wrsi=float(wr.iloc[-1])
    wrsi_prev=float(wr.iloc[-2])
    spy_close=spy["Close"]
    spy_aligned=spy_close.reindex(c.index,method="ffill")
    if len(spy_aligned)<22 or pd.isna(spy_aligned.iloc[-21]):
        raise ValueError("SPY 비교 데이터 부족")
    rel20=(price/float(c.iloc[-21])-1)-(float(spy_aligned.iloc[-1])/float(spy_aligned.iloc[-21])-1)
    atr_pct=float(d["ATR14"].iloc[-1]/price*100)
    if not all(map(math.isfinite,[price,dd,ma20,ma50,ma200,rsi,prev_rsi,vol_ratio,wrsi,wrsi_prev,rel20,atr_pct])):
        raise ValueError("일부 기술 지표 계산 불가")
    # Pullback (40): favor a moderate drawdown, penalize extreme drops and broken trends.
    if -25<=dd<=-10: pull=30
    elif -35<=dd< -25: pull=18
    elif -10<dd<=-5: pull=18
    elif -5<dd<=0: pull=8
    else: pull=5
    pull+=10 if price>=ma200*.95 else (5 if price>=ma200*.85 else 0)
    # Recovery (35)
    rebound=0
    rebound+=8 if 30<=rsi<=45 and rsi>prev_rsi else (4 if 40<=rsi<=55 and rsi>prev_rsi else 0)
    rebound+=8 if 40<=wrsi<=55 and wrsi>wrsi_prev else (4 if wrsi>wrsi_prev else 0)
    rebound+=7 if macd_up else 0
    rebound+=6 if price>ma20 else 0
    rebound+=6 if vol_ratio>=1.2 else (3 if vol_ratio>=1 else 0)
    # Market / relative strength (25), computed from SPY and candidate, not external narratives.
    spy_ma200=float(spy_close.tail(200).mean())
    market=10 if float(spy_close.iloc[-1])>spy_ma200 else 0
    market+=8 if rel20>0 else 0
    market+=7 if price>ma50 else 0
    score=pull+rebound+market
    leverage=symbol.upper() in LEVERAGED
    # Scores remain raw; leverage is an explicit caution, not a hidden penalty.
    opinion="매수 검토" if score>=80 else ("분할매수 검토" if score>=65 else ("반등 확인 대기" if score>=50 else "관망"))
    if leverage:
        opinion="고위험 · 별도 검토"
    risks=[]
    if price<ma200: risks.append("200일선 아래")
    if dd< -25: risks.append("52주 고점 대비 큰 하락")
    if rsi>=70: risks.append("일봉 RSI 과열")
    if atr_pct>=4: risks.append("변동성 높음")
    if leverage: risks.append("일일 레버리지·복리 효과로 장기 보유 위험")
    return {"ticker":symbol,"date":str(d.index[-1].date()),"score":score,
        "pullback":pull,"rebound":rebound,"market":market,"opinion":opinion,
        "drawdown":dd,"rsi":rsi,"weekly_rsi":wrsi,"relative20":rel20*100,
        "price":price,"ma200":ma200,"vol_ratio":vol_ratio,
        "leveraged":leverage,"risks":risks or ["일반적인 시장 하락 위험"]}

def score_watchlist(tickers):
    spy=_get("SPY")
    results,errors=[],[]
    for symbol in dict.fromkeys(tickers):
        try:
            results.append(score_one(symbol,spy))
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")
    return results,errors
