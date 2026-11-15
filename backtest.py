"""Five-year historical signal comparison. Research only; no trading."""
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np
from strategy import prices, indicators, latest_complete

HORIZONS = (5, 10, 20)

def run_backtest(tickers):
    cutoff = pd.Timestamp(datetime.now(ZoneInfo("America/New_York")).date()) - pd.DateOffset(years=5)
    errors = []
    market_frames = {}
    for key, ticker in (("vix", "^VIX"), ("yield", "^TNX"), ("spy", "SPY")):
        try:
            market_frames[key] = latest_complete(prices(ticker, period="7y"))
        except Exception as exc:
            raise ValueError(f"시장 데이터 {ticker} 다운로드 실패: {exc}")
    vix = market_frames["vix"]["Close"]
    yld = market_frames["yield"]["Close"]
    spy = market_frames["spy"]["Close"]
    # Today's yield is compared with the 10 PRECEDING trading sessions.
    yld_prev10 = yld.shift(1).rolling(10).mean()
    spy_ma200 = spy.rolling(200).mean()
    events = []
    for ticker in tickers:
        try:
            d = indicators(latest_complete(prices(ticker, period="7y")))
            if "Open" not in d.columns:
                raise ValueError("시가(Open) 데이터 없음")
            if len(d) < 35:
                raise ValueError("지표 계산에 필요한 데이터 부족")
            # As-of join: only market observations known on or before ETF date.
            m = pd.DataFrame(index=d.index)
            for col, series in (("vix", vix), ("yield", yld),
                                ("yield_prev10", yld_prev10),
                                ("spy", spy), ("spy_ma200", spy_ma200)):
                m[col] = series.reindex(d.index, method="ffill")
            for i in range(1, len(d)-1):
                date = d.index[i]
                if date < cutoff:
                    continue
                last, prev = d.iloc[i], d.iloc[i-1]
                market = m.iloc[i]
                if market.isna().any():
                    continue
                market_ok = (market["vix"] < 22 or market["yield"] <= market["yield_prev10"])
                if not market_ok:
                    continue
                rsi = pd.notna(prev["RSI"]) and pd.notna(last["RSI"]) and prev["RSI"] <= 35 and last["RSI"] > prev["RSI"]
                macd = bool(d["golden"].iloc[max(0,i-1):i+1].fillna(False).any())
                vol = pd.notna(last["vol_ratio"]) and last["vol_ratio"] >= 1.2
                bb = (pd.notna(prev["BB_lower"]) and pd.notna(last["BB_lower"])
                      and prev["Close"] < prev["BB_lower"] and last["Close"] >= last["BB_lower"])
                if sum((rsi,macd,vol,bb)) < 3:
                    continue
                spy_ok = market["spy"] > market["spy_ma200"]
                entry = float(d["Open"].iloc[i+1])
                if not np.isfinite(entry) or entry <= 0:
                    continue
                for strategy in (["A","B"] if spy_ok else ["A"]):
                    row = {"종목": ticker, "전략": strategy, "신호일": date.date().isoformat()}
                    for h in HORIZONS:
                        # Signal after day-i close; enter next session open, exit day i+h close.
                        row[f"{h}일 수익률"] = (float(d["Close"].iloc[i+h]) / entry - 1)*100 if i+h < len(d) else np.nan
                    events.append(row)
        except Exception as exc:
            errors.append(f"{ticker}: {exc}")
    event_df = pd.DataFrame(events, columns=["종목","전략","신호일"]+[f"{h}일 수익률" for h in HORIZONS])
    summary = []
    for strategy in ("A","B"):
        subset = event_df[event_df["전략"] == strategy]
        row = {"전략": "A 기존" if strategy == "A" else "B 개선", "매수 신호 횟수": len(subset)}
        for h in HORIZONS:
            s = subset[f"{h}일 수익률"].dropna()
            row[f"{h}일 표본"] = len(s)
            row[f"{h}일 승률(%)"] = round(float((s > 0).mean()*100), 2) if len(s) else None
            row[f"{h}일 평균 수익률(%)"] = round(float(s.mean()), 2) if len(s) else None
        summary.append(row)
    return pd.DataFrame(summary), event_df, errors, cutoff.date().isoformat()
