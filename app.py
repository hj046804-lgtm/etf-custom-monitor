import streamlit as st
import pandas as pd
import yfinance as yf
import hmac, re
from html import escape
from strategy import scan
from watchlist_store import load, save
st.set_page_config(page_title="나만의 ETF 매수 알림",page_icon="📈",layout="wide")
st.title("📈 나만의 ETF 매수 알림")
st.caption("선택한 ETF만 매일 검사 · 자동매수 없음 · 기술 조건 기반 매수 신호 · 시장 지표 참고용")
try:
    repo=st.secrets["GITHUB_REPO"]
    token=st.secrets["GITHUB_TOKEN"]
    password=st.secrets["ADMIN_PASSWORD"]
except Exception:
    st.error("Streamlit Secrets에 GITHUB_REPO, GITHUB_TOKEN, ADMIN_PASSWORD를 설정하세요.")
    st.stop()
if not st.session_state.get("ok"):
    with st.form("login"):
        pwd=st.text_input("관리 비밀번호",type="password")
        if st.form_submit_button("로그인"):
            if hmac.compare_digest(pwd,password):
                st.session_state.ok=True
                st.rerun()
            else: st.error("비밀번호가 틀렸습니다.")
    st.stop()
try:
    watch,sha=load(repo,token)
except Exception as e:
    st.error("종목 목록을 불러오지 못했습니다: "+str(e))
    st.stop()
watch.setdefault("etfs",[])
st.info("매수 신호: RSI·MACD·거래량·볼린저 4개 중 3개 이상 · VIX·10년물 금리·SPY 200일선은 참고용 (매수 판정 미반영)")
st.subheader("ETF 검색 및 추가")
q=st.text_input("ETF 이름 또는 티커 검색",placeholder="예: QQQ, SOXX, S&P 500")
results=[]
if q.strip():
    try:
        for x in yf.Search(q.strip(),max_results=20,news_count=0).quotes:
            if x.get("quoteType","").upper()=="ETF" and re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}",str(x.get("symbol","")).upper()):
                results.append((x["symbol"].upper(),x.get("shortname") or x.get("longname") or x["symbol"]))
    except Exception as e:
        st.warning("검색 오류: "+str(e))
if results:
    selected=st.selectbox("검색 결과",range(len(results)),format_func=lambda i:results[i][0]+" · "+results[i][1])
    if st.button("선택 ETF 추가",type="primary"):
        symbol,name=results[selected]
        if any(x["ticker"]==symbol for x in watch["etfs"]): st.warning("이미 등록된 ETF입니다.")
        else:
            watch["etfs"].append({"ticker":symbol,"name":name,"active":True})
            save(repo,token,watch,sha);st.rerun()
elif q.strip(): st.caption("검색 결과가 없습니다. 미국 ETF 이름이나 티커를 다시 입력하세요.")
st.subheader("내 모니터링 ETF")
if not watch["etfs"]: st.write("아직 등록한 ETF가 없습니다.")
for i,item in enumerate(watch["etfs"]):
    a,b,c=st.columns([4,2,1])
    a.write("**"+item["ticker"]+"** · "+item.get("name",""))
    enabled=b.checkbox("모니터링",value=item.get("active",True),key="on_"+item["ticker"])
    if enabled!=item.get("active",True):
        watch["etfs"][i]["active"]=enabled
        save(repo,token,watch,sha);st.rerun()
    if c.button("삭제",key="del_"+item["ticker"]):
        watch["etfs"].pop(i);save(repo,token,watch,sha);st.rerun()
active=[x["ticker"] for x in watch["etfs"] if x.get("active",True)]

st.divider()
st.subheader("📊 선택한 ETF 매수 조건 검사")
st.caption("미국 증시 완료 일봉 기준 · 선택한 활성 ETF만 검사 · 자동매수 없음")
with st.expander("📋 매수 조건 4개 + 시장 참고 지표"):
    st.markdown("""- **SPY 200일선:** SPY 종가와 200일 이동평균선 비교 (참고용, 매수 판정 미반영)
- **VIX:** 현재 수치 확인용 (매수 조건 미반영)
- **미국 10년물 금리:** 현재 수치 및 이전 10거래일 평균 참고용 (매수 조건 미반영)
- **RSI(14):** 전일 RSI 35 이하, 최근 RSI 상승
- **MACD:** 최근 2거래일 중 골든크로스
- **거래량:** 이전 20거래일 평균의 120% 이상
- **볼린저(20,2):** 전일 하단 이탈, 최근 재진입
**매수 신호:** 기술 4개 중 3개 이상 (VIX·금리·SPY 200일선은 참고용)""")
@st.cache_data(ttl=3600, show_spinner=False)
def cached_credit_spread():
    """Latest two published ICE BofA US High Yield OAS observations, with fallback."""
    import json
    from datetime import date, timedelta
    from urllib.request import Request, urlopen
    from io import StringIO
    errors = []
    observations = []
    # Primary source: FRED's public CSV. This endpoint may block cloud hosting.
    try:
        start = (date.today() - timedelta(days=35)).isoformat()
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2&cosd={start}"
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=10) as response:
            df = pd.read_csv(StringIO(response.read().decode("utf-8-sig")))
        dates = pd.to_datetime(df.iloc[:, 0], errors="coerce")
        values = pd.to_numeric(df["BAMLH0A0HYM2"], errors="coerce")
        observations = [(str(day.date()), float(val)) for day, val in zip(dates, values)
                        if pd.notna(day) and pd.notna(val)]
    except Exception as exc:
        errors.append(f"FRED: {type(exc).__name__}: {exc}")
    # Optional official FRED API fallback, if a FRED_API_KEY is configured.
    if len(observations) < 2:
        try:
            api_key = st.secrets.get("FRED_API_KEY")
            if api_key:
                from urllib.parse import urlencode
                params = urlencode({"series_id": "BAMLH0A0HYM2", "api_key": api_key,
                                    "file_type": "json", "sort_order": "desc", "limit": 15})
                url = "https://api.stlouisfed.org/fred/series/observations?" + params
                req = Request(url, headers={"User-Agent": "ETFMonitor/1.0"})
                with urlopen(req, timeout=12) as response:
                    payload = json.load(response)
                observations = [(item["date"], float(item["value"]))
                                for item in payload.get("observations", [])
                                if item.get("value") not in (None, ".")]
        except Exception as exc:
            errors.append(f"FRED API: {type(exc).__name__}: {exc}")
    # DBnomics mirrors the original FRED series; it is not an estimated substitute.
    if len(observations) < 2:
        try:
            url = "https://api.db.nomics.world/v22/series/FRED/BAMLH0A0HYM2?observations=1"
            req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            with urlopen(req, timeout=12) as response:
                payload = json.load(response)
            series = payload["series"]["docs"][0]
            observations = [(str(day), float(val)) for day, val in
                            zip(series["period"], series["value"])
                            if val is not None and str(val) not in ("NA", "NaN", "nan")]
        except Exception as exc:
            errors.append(f"DBnomics: {type(exc).__name__}: {exc}")
    observations = sorted(observations, key=lambda item: item[0])
    if len(observations) < 2:
        raise ValueError(" / ".join(errors) or "최근 유효 관측값 부족")
    (previous_date, previous), (current_date, current) = observations[-2:]
    if previous <= 0:
        raise ValueError("이전 관측값이 유효하지 않습니다")
    return {"value": current, "previous": previous,
            "change_pct": (current / previous - 1) * 100,
            "change_pp": current - previous,
            "date": current_date, "previous_date": previous_date}

@st.cache_data(ttl=900, show_spinner=False)
def cached_oil_prices():
    """Latest completed daily WTI and Brent futures closes, display-only."""
    result = {}
    for name, symbol in [("WTI", "CL=F"), ("브렌트유", "BZ=F")]:
        try:
            df = yf.download(symbol, period="1mo", interval="1d",
                             auto_adjust=True, progress=False, threads=False)
            if df.empty:
                raise ValueError("가격 데이터 없음")
            closes = df["Close"]
            if isinstance(closes, pd.DataFrame):
                closes = closes.iloc[:, 0]
            closes = closes.dropna()
            if len(closes) < 2:
                raise ValueError("비교할 종가 데이터 부족")
            latest, previous = float(closes.iloc[-1]), float(closes.iloc[-2])
            result[name] = {"price": latest, "change_pct": (latest / previous - 1) * 100,
                            "date": str(pd.Timestamp(closes.index[-1]).date())}
        except Exception as exc:
            result[name] = {"error": str(exc)}
    return result


@st.cache_data(ttl=3600, show_spinner=False)
def cached_vix3m_reference():
    """Cboe official daily VIX3M closing value; reference only."""
    import requests
    from io import StringIO
    url = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX3M_History.csv"
    response = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    lines = response.text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip().upper().startswith("DATE,"))
    df = pd.read_csv(StringIO("\n".join(lines[start:])))
    df.columns = [str(x).strip().upper() for x in df.columns]
    df["DATE"] = pd.to_datetime(df["DATE"])
    df["CLOSE"] = pd.to_numeric(df["CLOSE"], errors="coerce")
    df = df.dropna(subset=["DATE", "CLOSE"]).sort_values("DATE")
    if df.empty:
        raise ValueError("VIX3M 종가 데이터 없음")
    last = df.iloc[-1]
    return {"value": float(last["CLOSE"]), "date": str(last["DATE"].date())}

def vix_base_score(vix):
    """Illustrative SigmaRange-described VIX anchor scale, no confirmation bonuses."""
    if vix <= 15:
        return 33.0
    if vix < 20:
        return 33.0 + (vix - 15.0) * (34.0 / 5.0)
    if vix < 35:
        return 67.0 + (vix - 20.0) * (33.0 / 15.0)
    return 100.0


def clamp_score(value):
    return max(0.0, min(100.0, float(value)))

@st.cache_data(ttl=3600, show_spinner=False)
def cached_longterm_market():
    from strategy import latest_complete
    spy = latest_complete(yf.download("SPY", period="18mo", interval="1d", auto_adjust=True, progress=False, threads=False))
    close = spy["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = close.dropna()
    if len(close) < 252:
        raise ValueError("SPY 장기 가격 데이터 부족")
    current = float(close.iloc[-1])
    high = float(close.tail(252).max())
    ma200 = float(close.tail(200).mean())
    return {"date": str(close.index[-1].date()), "drawdown": (current / high - 1) * 100,
            "distance": (current / ma200 - 1) * 100}

@st.cache_data(ttl=3600, show_spinner=False)
def cached_sector_breadth():
    from strategy import latest_complete
    symbols = ["XLK","XLF","XLV","XLE","XLI","XLP","XLY","XLU","XLB","XLRE","XLC"]
    above, total, dates = 0, 0, []
    for symbol in symbols:
        try:
            df = latest_complete(yf.download(symbol, period="18mo", interval="1d", auto_adjust=True, progress=False, threads=False))
            close = df["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            close = close.dropna()
            if len(close) < 200:
                continue
            above += int(float(close.iloc[-1]) > float(close.tail(200).mean()))
            total += 1
            dates.append(str(close.index[-1].date()))
        except Exception:
            continue
    if total < 8 or len(set(dates)) != 1:
        raise ValueError("섹터 ETF 데이터 부족 또는 기준일 불일치")
    return {"above": above, "total": total, "date": dates[0]}

@st.cache_data(ttl=900,show_spinner=False)
def cached_scan(tickers, version="sigma-20day-v2"):
    return scan(list(tickers))
if st.button("🔄 최신 데이터 다시 확인",type="primary"):
    cached_scan.clear()
    cached_oil_prices.clear()
    cached_credit_spread.clear()
    cached_vix3m_reference.clear()
    cached_longterm_market.clear()
    cached_sector_breadth.clear()
if not active:
    st.info("모니터링할 ETF를 검색해서 추가하고 ON으로 설정해 주세요.")
else:
    with st.spinner("선택한 ETF와 시장 지표 분석 중..."):
        rows,market,errors=cached_scan(tuple(active))
    if not market:
        st.error("시장 데이터를 불러오지 못했습니다.")
        if errors: st.code("\\n".join(errors))
    else:
        # Oil prices appear in the top reference row, replacing the SPY closing-price tile.
        oil = cached_oil_prices()
        s1,s2,s3,s4 = st.columns(4)
        for col, name in ((s1, "WTI"), (s2, "브렌트유")):
            item = oil[name]
            if "error" in item:
                col.metric(f"{name} 원유 선물", "조회 실패")
            else:
                col.metric(f"{name} 원유 선물", f"${item['price']:,.2f}",
                           f"{item['change_pct']:+.2f}%")
                col.caption(f"기준일: {item['date']} · USD/배럴")
        s3.metric("SPY 200일 평균",f"${market['spy_ma200']:.2f}")
        s4.metric("SPY 추세 참고","200일선 위" if market["spy_trend_ok"] else "200일선 아래")
        c1,c2,c3,c4=st.columns(4)
        c1.metric("VIX (참고)",f"{market['vix']:.2f}")
        c2.metric("미국 10년물 금리 (참고)",f"{market['yield']:.2f}%")
        c3.metric("금리 이전 10일 평균",f"{market['yield_avg']:.2f}%")
        c4.metric("매수 신호 종목",f"{sum(r['signal'] for r in rows)}개")
        st.caption(f"SPY 기준일 {market['spy_date']} · VIX 기준일 {market['vix_date']} · 금리 기준일 {market['yield_date']} · ETF 기준일은 표에 표시")
        st.caption("WTI·브렌트유: 최근 선물 일봉 종가(지연 가능), 전 거래일 대비 등락률 · 매수 조건 및 텔레그램 알림에 미반영")
        # Visual-only dashboard: two-input calculation remains unchanged.
        vix_now = market["vix"]
        vix_score = vix_base_score(vix_now)
        try:
            vix3m = cached_vix3m_reference()
            if vix3m["date"] != market["vix_date"] or vix3m["value"] <= 0:
                raise ValueError(f"기준일 불일치: VIX {market['vix_date']} / VIX3M {vix3m['date']}")
            ratio = vix_now / vix3m["value"]
            ratio_score = clamp_score((ratio - 0.85) / 0.20 * 100)
            overall = 0.70 * vix_score + 0.30 * ratio_score
            zone = "BUY 관심" if overall >= 67 else "NEUTRAL" if overall >= 34 else "SELL 관심"
            zone_note = "공포가 높은 구간 · 매수 보장 아님" if overall >= 67 else "확인 신호 중립" if overall >= 34 else "공포가 낮은 구간 · 매도 보장 아님"
            # SVG semicircle: needle follows score on the 0-100 scale.
            import math
            theta = math.pi * (1 - overall / 100)
            nx = 180 + 136 * math.cos(theta)
            ny = 184 - 136 * math.sin(theta)
            gauge = f"""<svg viewBox="0 0 360 235" style="width:100%;max-width:420px;display:block;margin:0 auto" role="img" aria-label="BUY SELL 참고 점수 {overall:.0f}점">
              <path d="M 48 184 A 132 132 0 0 1 180 52" fill="none" stroke="#854252" stroke-width="18"/>
              <path d="M 180 52 A 132 132 0 0 1 267 85" fill="none" stroke="#9ca3af" stroke-width="18"/>
              <path d="M 267 85 A 132 132 0 0 1 312 184" fill="none" stroke="#28735b" stroke-width="18"/>
              <circle cx="{nx:.1f}" cy="{ny:.1f}" r="12" fill="#111827" stroke="#d1d5db" stroke-width="6"/>
              <text x="180" y="161" text-anchor="middle" font-size="54" font-weight="700" fill="#f4f5f8">{overall:.0f}<tspan font-size="20" fill="#aab0be">/100</tspan></text>
              <text x="180" y="191" text-anchor="middle" font-size="14" fill="#b4bbca">VIX {vix_now:.2f}</text>
              <text x="43" y="214" font-size="14" fill="#b9bfcc">SELL</text>
              <text x="278" y="214" font-size="14" fill="#b9bfcc">BUY</text>
              <text x="80" y="53" font-size="12" fill="#aeb5c4">VIX 15</text>
              <text x="262" y="53" font-size="12" fill="#aeb5c4">VIX 20</text>
            </svg>"""
            st.markdown(f"""
            <div style="background:linear-gradient(145deg,#242a37,#191e2b);border:1px solid #3b4252;border-radius:28px;padding:24px 20px;color:#e9ecf4;margin:16px 0">
              <div style="font-size:23px;font-weight:750">◉ BUY &amp; SELL Indicator</div>
              <div style="color:#aeb5c4;font-size:13px;margin:7px 0 16px">VIX + VIX3M 기반 · 완료 일봉 · 자체 참고 점수</div>
              {gauge}
              <div style="text-align:center;margin:-4px 0 20px"><span style="border:1px solid #646a78;background:#343947;border-radius:16px;padding:8px 17px;font-weight:700">{zone}</span><span style="color:#b8bfcd;margin-left:10px;font-size:13px">{zone_note}</span></div>
              <div style="border-top:1px solid #3b4252;padding-top:18px;font-size:15px">
                <div style="display:flex;justify-content:space-between;gap:10px;margin-bottom:13px"><span style="color:#b7bfce">VIX 공포지수 · 70%</span><strong>{vix_now:.2f} · {vix_score:.0f}점</strong></div>
                <div style="display:flex;justify-content:space-between;gap:10px"><span style="color:#b7bfce">기간구조 VIX÷VIX3M · 30%</span><strong>{ratio:.3f} · {ratio_score:.0f}점</strong></div>
              </div>
              <div style="color:#929cac;font-size:12px;margin-top:19px">데이터 기준 {escape(str(vix3m["date"]))} · VIX3M {vix3m["value"]:.2f}</div>
            </div>
            """, unsafe_allow_html=True)
        except Exception as exc:
            st.markdown('<div style="background:#242a37;border:1px solid #3b4252;border-radius:24px;padding:24px;color:#eef0f6"><b style="font-size:23px">◉ BUY &amp; SELL Indicator</b><p>VIX + VIX3M 기반 · 종합 점수 확인 불가</p></div>', unsafe_allow_html=True)
            st.warning(f"VIX3M 확인 불가: {exc}. 종합 점수를 표시하지 않습니다.")
        st.caption("VIX 70% + VIX/VIX3M 30% · 0~33 SELL 관심 / 34~66 NEUTRAL / 67~100 BUY 관심 · 점수는 시장 공포 참고용이며 매수·매도 신호나 상승 확률이 아닙니다. 기존 ETF 매수 조건 및 알림에는 영향이 없습니다.")
        st.subheader("🏦 하이일드 신용스프레드 참고")
        st.caption("FRED · ICE BofA US High Yield OAS · 최신 발표된 두 관측일 비교 · 매수 조건과 알림에 미반영")
        try:
            credit = cached_credit_spread()
            credit_cols = st.columns(2)
            credit_cols[0].metric("하이일드 신용스프레드", f"{credit['value']:.2f}%p",
                                  f"{credit['change_pct']:+.2f}% (전 관측일 대비)",
                                  delta_color="inverse")
            credit_cols[1].metric("실제 스프레드 변화", f"{credit['change_pp']:+.2f}%p",
                                  "확대 · 위험 증가 가능" if credit["change_pp"] > 0 else
                                  "축소 · 위험 완화 가능" if credit["change_pp"] < 0 else "변화 없음")
            st.caption(f"최근 발표일: {credit['date']} · 비교일: {credit['previous_date']} · 발표 지연 가능 · 전 거래일이 아닌 전 관측일 기준")
        except Exception as exc:
            st.warning("하이일드 신용스프레드 데이터를 가져오지 못했습니다. 잠시 후 다시 확인해 주세요.")
            st.caption(f"조회 오류: {type(exc).__name__}: {exc}")
            st.caption("FRED API 키를 Streamlit Secrets의 FRED_API_KEY에 등록하면 공식 API 경로도 사용할 수 있습니다.")
        st.subheader("🔔 현재 매수 신호")
        signals=[r for r in rows if r["signal"]]
        if signals:
            for r in signals:
                st.success(f"**{r['ticker']}** · {r['date']} · 기술 조건 {r['technical_count']}/4 · 종가 ${r['close']:.2f}")
        else: st.write("현재 조건을 충족하는 ETF가 없습니다.")
        st.subheader("📐 20일 이동평균 시그마(σ) 모니터")
        st.caption("최근 20거래일 종가 평균을 0σ로 두고 현재 종가의 상대적 위치를 표시합니다. SigmaRange와 계산법은 다릅니다.")
        if rows:
            sigma_display=[]
            for r in rows:
                z=r.get("sigma_score")
                status=("과매도 (−1.5σ 이하)" if z <= -1.5 else "−1σ 이하" if z <= -1 else
                        "과열 (+1.5σ 이상)" if z >= 1.5 else "+1σ 이상" if z >= 1 else "정상 범위") if z is not None else "계산 불가"
                sigma_display.append({
                    "ETF":r["ticker"],"기준일":r["date"],
                    "종가($)":round(r["close"],2),
                    "시그마(σ)":round(z,2) if z is not None else None,
                    "구간":status,
                    "−1σ 하단($)":round(r["sigma_lower"],2) if r.get("sigma_lower") is not None else None,
                    "+1σ 상단($)":round(r["sigma_upper"],2) if r.get("sigma_upper") is not None else None,
                    "20일 평균가($)":round(r["sigma_anchor"],2) if r.get("sigma_anchor") is not None else None,
                    "20일 범위 위치(%)":round(r["position20_pct"],1) if r.get("position20_pct") is not None else None,
                })
            sigma_df=pd.DataFrame(sigma_display)
            filter_status=st.selectbox("시그마 구간 필터",["전체","과매도 (−1.5σ 이하)","−1σ 이하","정상 범위","+1σ 이상","과열 (+1.5σ 이상)"])
            if filter_status!="전체": sigma_df=sigma_df[sigma_df["구간"]==filter_status]
            st.markdown("""
<style>
.sigma-card{background:#19202c;border:1px solid #374151;border-radius:16px;padding:16px 18px;margin:10px 0;color:#f1f5f9}
.sigma-head{display:flex;align-items:baseline;justify-content:space-between;gap:8px;flex-wrap:wrap}
.sigma-name{font-weight:800;font-size:1.2rem}.sigma-price{font-weight:800;font-size:1.2rem}
.sigma-change{font-weight:650;font-size:.94rem;margin-left:8px}
.sigma-track{height:13px;position:relative;border-radius:20px;margin:24px 8px 15px;background:linear-gradient(90deg,#456b9e 0%,#6b8aa1 25%,#89979a 50%,#b19c76 75%,#a45460 100%)}
.sigma-track:before,.sigma-track:after{content:"";position:absolute;top:-4px;height:21px;width:2px;background:#d7dee7;opacity:.45}
.sigma-track:before{left:25%}.sigma-track:after{left:75%}
.sigma-dot{position:absolute;top:50%;height:23px;width:23px;transform:translate(-50%,-50%);border-radius:50%;background:#a7b2c4;border:3px solid #111827;box-shadow:0 0 0 2px #637287}
.sigma-foot{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;color:#c3cbd8;font-size:.84rem}
.sigma-score{font-size:1.1rem;font-weight:800;color:#f1f5f9}
</style>""",unsafe_allow_html=True)
            for _,item in sigma_df.iterrows():
                source=next((r for r in rows if r["ticker"]==item["ETF"]),None)
                if source is None: continue
                z=source.get("sigma_score")
                anchor=source.get("sigma_anchor")
                unit=source.get("sigma_unit")
                change=source.get("daily_change_pct")
                if z is None or anchor is None or unit is None or unit <= 0:
                    st.info(f"{source['ticker']}: 시그마 계산에 필요한 데이터가 부족합니다.")
                    continue
                # -2 sigma to +2 sigma on a fixed horizontal scale.
                pct=max(0.0,min(100.0,(z+2)/4*100))
                lower=max(0.0,anchor-2*unit)
                upper=anchor+2*unit
                change_text=f"{change:+.2f}%" if change is not None else "—"
                change_color="#44c7a2" if change is not None and change>=0 else "#ef7884"
                ticker=escape(str(source["ticker"]))
                card=(f'<div class="sigma-card"><div class="sigma-head">'
                      f'<span class="sigma-name">{ticker}</span>'
                      f'<span><span class="sigma-price">${source["close"]:,.2f}</span>'
                      f'<span class="sigma-change" style="color:{change_color}">{change_text}</span></span></div>'
                      f'<div class="sigma-track"><span class="sigma-dot" style="left:{pct:.1f}%"></span></div>'
                      f'<div class="sigma-foot"><span class="sigma-score">{z:+.2f}σ</span>'
                      f'<span>${lower:,.2f} – ${upper:,.2f} · ±2σ</span></div></div>')
                st.markdown(card,unsafe_allow_html=True)
            with st.expander("시그마 상세 수치 표 보기"):
                st.dataframe(sigma_df,hide_index=True,use_container_width=True)
            with st.expander("σ 계산법과 해석"):
                st.write("0σ = 최근 20거래일 종가의 평균(오늘 완료된 일봉 포함). 1σ = 같은 20개 종가의 모집단 표준편차(ddof=0). σ 점수 = (현재 종가 − 20일 평균) ÷ 20일 표준편차.")
                st.warning("σ는 현재 가격의 상대적 위치를 나타내며 실제 저점·고점, 상승·하락 확률이나 향후 가격 범위를 보장하지 않습니다. 기존 매수 조건과 텔레그램 알림에는 반영되지 않습니다.")
        st.subheader("📊 전체 ETF 검사 결과")
        if rows:
            display=[]
            for r in sorted(rows,key=lambda x:(not x["signal"],-x["technical_count"],x["ticker"])):
                display.append({"종목":r["ticker"],"기준일":r["date"],"매수 신호":"🟢 발생" if r["signal"] else "—",
                    "SPY 추세(참고)":"위" if market["spy_trend_ok"] else "아래","기술 충족":f"{r['technical_count']}/4",
                    "RSI 반등":"✅" if r["rsi_ok"] else "❌","MACD":"✅" if r["macd_ok"] else "❌",
                    "거래량 120%":"✅" if r["volume_ok"] else "❌","볼린저":"✅" if r["bb_ok"] else "❌",
                    "RSI 값":round(r["rsi"],1),"거래량 배수":round(r["volume_ratio"],2) if r["volume_ratio"] is not None else None})
            frame=pd.DataFrame(display)
            st.dataframe(frame,hide_index=True,use_container_width=True)
            st.download_button("📥 검사 결과 CSV",frame.to_csv(index=False).encode("utf-8-sig"),"etf_signals.csv","text/csv")
        if errors:
            with st.expander(f"⚠️ 데이터 조회 실패 {len(errors)}건"):
                st.code("\\n".join(errors))
st.warning("알림은 GitHub Actions에서 별도로 검사해 텔레그램으로 전송합니다. 무료 서비스 실행 지연이나 실패가 발생할 수 있습니다.")
