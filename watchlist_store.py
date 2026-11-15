import base64, json, requests
URL = "https://api.github.com/repos/{}/contents/watchlist.json"
def load(repo, token):
    r=requests.get(URL.format(repo),headers={"Authorization":"Bearer "+token},timeout=20);r.raise_for_status()
    data=r.json()
    return json.loads(base64.b64decode(data["content"])),data["sha"]
def save(repo,token,data,sha):
    raw=json.dumps(data,ensure_ascii=False,indent=2).encode()
    r=requests.put(URL.format(repo),headers={"Authorization":"Bearer "+token},json={"message":"Update ETF watchlist","content":base64.b64encode(raw).decode(),"sha":sha},timeout=20)
    r.raise_for_status()
