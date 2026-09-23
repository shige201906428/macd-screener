"""S&P500(約503銘柄)の直近終値時点のMACDを計算し data.json に出力する。
GitHub Actions から米国市場の引け後に毎営業日実行する想定。
MACD = 12日EMA - 26日EMA、ヒストグラム = MACD - シグナル(9日EMA)。
"""
import io
import json
import datetime as dt
import urllib.request
from pathlib import Path

import pandas as pd
import yfinance as yf

EX_CACHE = Path("exchanges.json")  # 取引所コードのキャッシュ(初回のみ全件取得)
EX_NAME = {"NYQ": "NYSE", "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ"}


def load_constituents() -> pd.DataFrame:
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (macd-screener)"})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    df = pd.read_html(io.StringIO(html))[0]
    df["yf"] = df["Symbol"].str.replace(".", "-", regex=False)  # BRK.B -> BRK-B
    return df


def macd_last(close: pd.Series) -> tuple[float, float]:
    e12 = close.ewm(span=12, adjust=False).mean()
    e26 = close.ewm(span=26, adjust=False).mean()
    m = e12 - e26
    s = m.ewm(span=9, adjust=False).mean()
    return float(m.iloc[-1]), float((m - s).iloc[-1])


def main() -> None:
    cons = load_constituents()
    tickers = cons["yf"].tolist()

    ex = json.loads(EX_CACHE.read_text()) if EX_CACHE.exists() else {}
    for t in tickers:
        if ex.get(t):
            continue
        try:
            ex[t] = yf.Ticker(t).fast_info["exchange"]
        except Exception:
            ex[t] = ""
    EX_CACHE.write_text(json.dumps(ex, indent=0))

    px = yf.download(tickers, period="1y", auto_adjust=True, progress=False)["Close"]

    rows = []
    for _, r in cons.iterrows():
        t = r["yf"]
        if t not in px.columns:
            continue
        s = px[t].dropna()
        if len(s) < 60:
            continue
        m, h = macd_last(s)
        rows.append({
            "t": t,
            "n": r["Security"],
            "s": r["GICS Sector"],
            "e": EX_NAME.get(ex.get(t, ""), ex.get(t, "") or "不明"),
            "c": round(float(s.iloc[-1]), 2),
            "m": round(m, 4),
            "h": round(h, 4),
            "d": s.index[-1].strftime("%Y-%m-%d"),
        })

    # 取得失敗で大量欠損したデータで上書きしない
    if len(rows) < 450:
        raise SystemExit(f"取得できた銘柄が少なすぎます({len(rows)}件)。data.json は更新しません。")

    out = {
        "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "asof": max(r["d"] for r in rows),
        "count": len(rows),
        "rows": rows,
    }
    Path("data.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(rows)}銘柄を出力しました(基準日 {out['asof']})")


if __name__ == "__main__":
    main()
