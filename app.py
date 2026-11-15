import streamlit as st
import pandas as pd
import yfinance as yf
import hmac, re
from strategy import scan
from watchlist_store import load, save
st.set_page_config(page_title="나만의 ETF 매수 알림",page_icon="📈",layout="wide")
st.title("📈 나만의 ETF 매수 알림")
st.caption("선택한 ETF만 매일 검사 · 자동매수 없음 · 기존 매수 조건 유지")
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
st.info("매수 신호: VIX < 22 또는 미국 10년물 금리 ≤ 이전 10거래일 평균, 그리고 RSI·MACD·거래량·볼린저 4개 중 3개 이상")
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
st.subheader("최신 매수 조건 검사")
st.caption("미국 증시 완료 일봉 기준. 자동 알림은 GitHub Actions가 별도로 실행합니다.")
if st.button("지금 검사",disabled=not active):
    with st.spinner("시세와 지표를 확인하고 있어요..."):
        rows,market,errors=scan(active)
    if market:
        st.write("VIX:",round(market["vix"],2),"· 10년물 금리:",round(market["yield"],2),"%")
        st.dataframe(pd.DataFrame([{"ETF":r["ticker"],"일봉":r["date"],"매수 신호":"🔔" if r["signal"] else "—","기술 조건":str(r["technical_count"])+"/4","RSI":r["rsi_ok"],"MACD":r["macd_ok"],"거래량":r["volume_ok"],"볼린저":r["bb_ok"]} for r in rows]),hide_index=True,use_container_width=True)
    if errors: st.warning("\n".join(errors))
st.caption("무료 데이터는 지연·누락될 수 있으며 알림은 투자 권유가 아닙니다.")
