import streamlit as st
import pandas as pd
import yfinance as yf
import hmac, re
from strategy import scan
from watchlist_store import load, save
st.set_page_config(page_title="나만의 ETF 매수 알림",page_icon="📈",layout="wide")
st.title("📈 나만의 ETF 매수 알림")
st.caption("선택한 ETF만 매일 검사 · 자동매수 없음 · 기존 매수 신호 · SPY 200일선 참고용")
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
st.info("매수 신호: (VIX < 22 또는 10년물 금리 ≤ 이전 10일 평균) + 기술 4개 중 3개 이상 · SPY 200일선은 참고용")
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
with st.expander("📋 매수 조건 6개 + SPY 참고 지표"):
    st.markdown("""- **SPY 200일선:** SPY 종가와 200일 이동평균선 비교 (참고용, 매수 판정 미반영)
- **VIX:** 22 미만
- **미국 10년물 금리:** 이전 10거래일 평균 이하
- **RSI(14):** 전일 RSI 35 이하, 최근 RSI 상승
- **MACD:** 최근 2거래일 중 골든크로스
- **거래량:** 이전 20거래일 평균의 120% 이상
- **볼린저(20,2):** 전일 하단 이탈, 최근 재진입
**매수 신호:** VIX/금리 중 1개 이상 + 기술 4개 중 3개 이상 (SPY 200일선은 참고용)""")
@st.cache_data(ttl=900,show_spinner=False)
def cached_scan(tickers):
    return scan(list(tickers))
if st.button("🔄 최신 데이터 다시 확인",type="primary"):
    cached_scan.clear()
if not active:
    st.info("모니터링할 ETF를 검색해서 추가하고 ON으로 설정해 주세요.")
else:
    with st.spinner("선택한 ETF와 시장 지표 분석 중..."):
        rows,market,errors=cached_scan(tuple(active))
    if not market:
        st.error("시장 데이터를 불러오지 못했습니다.")
        if errors: st.code("\\n".join(errors))
    else:
        s1,s2,s3=st.columns(3)
        s1.metric("SPY 종가",f"${market['spy_close']:.2f}")
        s2.metric("SPY 200일 평균",f"${market['spy_ma200']:.2f}")
        s3.metric("SPY 추세 참고","200일선 위" if market["spy_trend_ok"] else "200일선 아래")
        c1,c2,c3,c4=st.columns(4)
        c1.metric("VIX",f"{market['vix']:.2f}","충족" if market['vix_ok'] else "미충족")
        c2.metric("미국 10년물 금리",f"{market['yield']:.2f}%","충족" if market['yield_ok'] else "미충족")
        c3.metric("금리 이전 10일 평균",f"{market['yield_avg']:.2f}%")
        c4.metric("매수 신호 종목",f"{sum(r['signal'] for r in rows)}개")
        st.caption(f"SPY 기준일 {market['spy_date']} · VIX 기준일 {market['vix_date']} · 금리 기준일 {market['yield_date']} · ETF 기준일은 표에 표시")
        st.subheader("🔔 현재 매수 신호")
        signals=[r for r in rows if r["signal"]]
        if signals:
            for r in signals:
                st.success(f"**{r['ticker']}** · {r['date']} · 기술 조건 {r['technical_count']}/4 · 종가 ${r['close']:.2f}")
        else: st.write("현재 조건을 충족하는 ETF가 없습니다.")
        st.subheader("📊 전체 ETF 검사 결과")
        if rows:
            display=[]
            for r in sorted(rows,key=lambda x:(not x["signal"],-x["technical_count"],x["ticker"])):
                display.append({"종목":r["ticker"],"기준일":r["date"],"매수 신호":"🟢 발생" if r["signal"] else "—",
                    "시장 조건":"✅" if r["market_ok"] else "❌","SPY 추세(참고)":"위" if market["spy_trend_ok"] else "아래","기술 충족":f"{r['technical_count']}/4",
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


st.divider()
st.subheader("🧪 최근 5년 전략 백테스트 · 10일 / 30일 / 90일")
st.success("✅ 백테스트 최신 버전: 10·30·90거래일 (v2)")
st.caption("A 기존: VIX/금리 중 1개 + 기술 3/4 · B 개선: A + SPY 200일선 위. 신호일 종가 확인 후 다음 거래일 시가 매수, 신호일로부터 10·30·90거래일째 종가 청산. 배당·수수료·슬리피지 미반영.")
st.caption("ETF별 출시일에 따라 분석 가능한 기간이 다르며, 동일 종목의 연속 신호도 각각 집계합니다. 과거 성과는 미래 수익을 보장하지 않습니다.")
@st.cache_data(ttl=86400,show_spinner=False)
def cached_backtest(tickers, version="10-30-90-v2"):
    from backtest import run_backtest
    return run_backtest(list(tickers))
if st.button("▶️ 5년 백테스트 실행",key="run_backtest"):
    if not active:
        st.warning("활성 ETF를 먼저 등록해 주세요.")
    else:
        st.session_state["show_backtest"]=True
if st.session_state.get("show_backtest") and active:
    with st.spinner("과거 10년 데이터를 불러와 5년간의 신호를 계산 중입니다. 종목 수에 따라 시간이 걸립니다..."):
        try:
            bt_summary, bt_events, bt_errors, bt_start = cached_backtest(tuple(active), "10-30-90-v2")
            st.write(f"분석 시작일: {bt_start} · 활성 ETF {len(active)}개")
            st.dataframe(bt_summary,hide_index=True,use_container_width=True)
            st.caption("승률은 수익률 > 0인 신호의 비율이며, 미완료 보유기간은 해당 기간 표본에서 제외됩니다.")
            if len(bt_events):
                by_ticker = bt_events.groupby(["종목","전략"],as_index=False).agg(신호횟수=("신호일","count"))
                st.subheader("종목별 신호 횟수")
                st.dataframe(by_ticker,hide_index=True,use_container_width=True)
                with st.expander("전체 매수 신호별 수익률"):
                    st.dataframe(bt_events,hide_index=True,use_container_width=True)
                st.download_button("📥 백테스트 상세 CSV",bt_events.to_csv(index=False).encode("utf-8-sig"),"etf_backtest_5y.csv","text/csv")
            else:
                st.info("해당 기간에 매수 신호가 없었습니다.")
            if bt_errors:
                st.warning("일부 ETF 데이터를 조회하지 못했습니다: "+"; ".join(bt_errors))
        except Exception as exc:
            st.error("백테스트 실행 실패: "+str(exc))
