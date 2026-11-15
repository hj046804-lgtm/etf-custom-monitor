"""Daily alerts for user-selected active ETFs only."""
import os,json,requests,sys
from pathlib import Path
from strategy import scan
STATE=Path("alert_state.json")
def main():
    token=os.getenv("TELEGRAM_BOT_TOKEN")
    chat=os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat: raise RuntimeError("Telegram GitHub Secrets missing")
    if os.getenv("TELEGRAM_TEST") == "1":
        response=requests.post("https://api.telegram.org/bot"+token+"/sendMessage",json={"chat_id":chat,"text":"🔔 [맞춤 ETF 모니터] 텔레그램 연결 테스트 성공!\n이 메시지는 테스트이며 실제 매수 신호가 아닙니다."},timeout=20)
        response.raise_for_status()
        print("Telegram test message sent")
        return
    watch=json.loads(Path("watchlist.json").read_text(encoding="utf-8"))
    etfs=list(dict.fromkeys(x["ticker"] for x in watch.get("etfs",[]) if x.get("active",True)))
    if not etfs:
        print("No active ETFs; nothing to scan")
        return
    rows,market,errors=scan(etfs)
    if not market or errors or len(rows)!=len(etfs):
        raise RuntimeError("Incomplete scan: "+repr(errors))
    state=json.loads(STATE.read_text()) if STATE.exists() else {}
    for r in rows:
        if not r["signal"]: continue
        key=r["ticker"]+":"+r["date"]
        if key in state: continue
        checks=[name for name,ok in [("RSI",r["rsi_ok"]),("MACD",r["macd_ok"]),("거래량",r["volume_ok"]),("볼린저",r["bb_ok"])] if ok]
        msg=("🔔 [맞춤 ETF 모니터] 매수 조건 충족\n종목: "+r["ticker"]+"\n기준일: "+r["date"]+
             "\n종가: $"+format(r["close"],".2f")+"\n기술 조건: "+str(r["technical_count"])+
             "/4\n충족: "+", ".join(checks)+"\nVIX: "+format(market["vix"],".2f")+
             "\n10년물 금리: "+format(market["yield"],".2f")+"%\n※ 투자 참고용 조건 알림")
        response=requests.post("https://api.telegram.org/bot"+token+"/sendMessage",json={"chat_id":chat,"text":msg},timeout=20)
        response.raise_for_status()
        state[key]=True
        STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n")
        print("Sent",key)
    print("Checked",len(rows),"ETFs")
if __name__=="__main__": main()
