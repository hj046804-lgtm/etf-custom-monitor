"""Free, rules-based US ETF market screener. No paid AI/API required."""
import numpy as np
import pandas as pd
import yfinance as yf
from strategy import latest_complete, indicators

# Broad, curated liquid US ETF universe; not literally every listed ETF.
UNIVERSE = list(dict.fromkeys("""
SPY QQQ DIA IWM VTI VOO IVV RSP SCHD VIG VYM DGRO SPLG
XLK XLF XLV XLE XLI XLP XLY XLU XLB XLRE XLC
SMH SOXX XBI IBB IHI XME ITA XAR KRE KBE
ARKK ARKW IGV SKYY HACK BOTZ ROBO CLOU
EEM EFA VWO IEMG EWJ EWZ FXI INDA MCHI
GLD IAU SLV GDX GDXJ USO DBC PDBC
TLT IEF SHY SGOV BND AGG LQD HYG TIP
VNQ SCHH XHB ITB XRT XOP TAN ICLN
MTUM QUAL USMV SPLV VTV IWF IWD
""".split()))

def _frame(symbol):
    data = yf.download(symbol, period="18mo", interval="1d",
                       auto_adjust=True, progress=False, threads=False)
    if data.empty:
        raise ValueError("가격 데이터 없음")
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    return latest_complete(data).dropna(subset=["Close"]).sort_index()

def screen(limit=5):
    results, failed = [], 0
    for symbol in UNIVERSE:
        try:
            d = _frame(symbol)
            if len(d) < 210 or not {"High","Low","Volume"}.issubset(d.columns):
                failed += 1
                continue
            d = indicators(d)
            close = d["Close"]
            last = d.iloc[-1]
            price = float(close.iloc[-1])
            ma20 = float(close.tail(20).mean())
            ma50 = float(close.tail(50).mean())
            ma200 = float(close.tail(200).mean())
            ret20 = (price / float(close.iloc[-21]) - 1) * 100
            ret60 = (price / float(close.iloc[-61]) - 1) * 100
            vol = float(d["Volume"].tail(20).mean() * price)
            if not np.isfinite(vol) or vol < 2_000_000 or price < 3:
                continue
            # ATR% measures risk; reward recent strength and long-term trend.
            atr_pct = float(last["ATR14"] / price * 100)
            if not np.isfinite(atr_pct):
                continue
            rsi = float(last["RSI"])
            if not np.isfinite(rsi):
                continue
            score = (22 if price > ma200 else 0) + (16 if ma50 > ma200 else 0)
            score += (12 if price > ma20 else 0) + (12 if price > ma50 else 0)
            score += (12 if ret20 > 0 else 0) + (10 if ret60 > 0 else 0)
            score += (8 if 40 <= rsi <= 68 else 0)
            score += (8 if last["MACD"] > last["MACD_signal"] else 0)
            score -= (12 if rsi >= 75 else 0) + (10 if atr_pct > 5 else 0)
            score -= (12 if ret20 < -8 else 0)
            score = max(0, min(100, int(score)))
            opinion = "매수 검토" if score >= 78 else ("관심·관찰" if score >= 60 else "관망")
            positives = []
            if price > ma200: positives.append("200일선 위")
            if ma50 > ma200: positives.append("중기 상승 추세")
            if ret20 > 0: positives.append("최근 20거래일 상승")
            if last["MACD"] > last["MACD_signal"]: positives.append("MACD 우위")
            risks = []
            if rsi >= 70: risks.append("RSI 과열 주의")
            if atr_pct > 4: risks.append("변동성 높음")
            if price < ma200: risks.append("장기 하락 추세")
            if not risks: risks.append("시장 급변·갭 하락 가능")
            results.append({"ticker":symbol,"date":str(d.index[-1].date()),
                "score":score,"opinion":opinion,"price":price,"rsi":rsi,
                "ret20":ret20,"ret60":ret60,"atr_pct":atr_pct,
                "reason":", ".join(positives) or "뚜렷한 상승 근거 부족",
                "risk":", ".join(risks)})
        except Exception:
            failed += 1
    return sorted(results,key=lambda x:(x["score"],x["ret20"]),reverse=True)[:limit],len(results),failed,len(UNIVERSE)

def market_comment(market):
    if not market:
        return "시장 참고 지표를 가져오지 못해 시황 판단을 보류합니다."
    vix = market.get("vix")
    trend = market.get("spy_trend_ok")
    y = market.get("yield")
    avg = market.get("yield_avg")
    parts = ["SPY가 200일선 위에 있어 장기 추세가 우호적입니다." if trend else
             "SPY가 200일선 아래에 있어 시장 하락 위험에 유의해야 합니다."]
    if vix is not None:
        parts.append(f"VIX {vix:.1f}: " + ("변동성 경계 구간입니다." if vix >= 25 else "변동성이 높은 편입니다." if vix >= 20 else "상대적으로 안정적인 구간입니다."))
    if y is not None and avg is not None:
        parts.append(f"미국 10년물 금리 {y:.2f}%, 최근 10거래일 평균 {avg:.2f}%로 " +
                     ("평균보다 높습니다." if y > avg else "평균 이하입니다."))
    return " ".join(parts)
