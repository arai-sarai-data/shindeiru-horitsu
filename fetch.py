"""死んでいる法律発見器：e-Gov法令API（Version 2）から現行の全法律を取り、
最後に改正されてから長い年月がたっている法律・一度も改正されていない法律を並べる。"""
import datetime as dt
import re
from collections import Counter

from lib import oc

API = "https://laws.e-gov.go.jp/api/2/laws"
PAGE = "https://laws.e-gov.go.jp/"
TODAY = dt.date.today()


def pick(d, *keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return None


def date(s):
    if not s:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(s))
    return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def era(d):
    if d is None:
        return ""
    for y0, name in ((2019, "令和"), (1989, "平成"), (1926, "昭和"), (1912, "大正"), (1868, "明治")):
        if d.year >= y0:
            return name
    return ""


def run():
    laws, off = [], 0
    while True:
        j = oc.get(API, params={"law_type": "Act", "limit": 500, "offset": off, "response_format": "json"},
                   as_json=True, cache=None)
        items = j.get("laws") or []
        laws += items
        total = j.get("total_count") or 0
        oc.log("laws", len(laws), "/", total)
        nxt = j.get("next_offset")
        if not items or nxt in (None, off) or len(laws) >= total:
            break
        off = nxt
    oc.check(len(laws) > 1500, "法律の件数が少なすぎます(%d)" % len(laws))

    rows = []
    for x in laws:
        info = x.get("law_info") or {}
        rev = x.get("revision_info") or x.get("current_revision_info") or {}
        title = pick(rev, "law_title") or pick(info, "law_title")
        lid = pick(info, "law_id")
        prom = date(pick(info, "promulgation_date"))
        amend = date(pick(rev, "amendment_promulgate_date"))
        status = str(pick(rev, "repeal_status") or "")
        if not title or not lid or prom is None:
            continue
        if status and status not in ("None", "none", ""):
            continue  # 廃止・失効は除く
        last = amend or prom
        never = amend is None or amend <= prom
        rows.append({"law": title, "law_url": "https://laws.e-gov.go.jp/law/%s" % lid, "num": pick(info, "law_num") or "",
                     "prom": prom.isoformat(), "last": last.isoformat(), "years": round((TODAY - last).days / 365.25, 1),
                     "age": round((TODAY - prom).days / 365.25, 1), "never": never, "era": era(prom)})
    oc.check(len(rows) > 1500, "現行法律の件数が少なすぎます(%d)" % len(rows))
    oc.check(sum(1 for r in rows if r["never"]) < len(rows) * 0.9, "改正日が取れていない可能性があります")

    cols = [{"key": "law", "label": "法律名", "type": "link"},
            {"key": "years", "label": "最後の改正からの年数", "type": "num", "fmt": "1", "bar": True},
            {"key": "last", "label": "最後の改正（公布）"}, {"key": "prom", "label": "公布日"}, {"key": "num", "label": "法令番号"}]
    cols2 = [{"key": "law", "label": "法律名", "type": "link"},
             {"key": "age", "label": "公布からの年数", "type": "num", "fmt": "1", "bar": True},
             {"key": "prom", "label": "公布日"}, {"key": "num", "label": "法令番号"}]
    stale = sorted(rows, key=lambda r: -r["years"])
    never = sorted([r for r in rows if r["never"]], key=lambda r: -r["age"])
    era_c = Counter(r["era"] for r in rows if r["years"] >= 50)
    by_era = [{"era": k, "n": v} for k, v in era_c.most_common()]
    meth = ("e-Gov法令APIで現行の法律（政令・省令を除く）を取得し、最後の改正法の公布日から今日までの年数を数えました。"
            "改正されていない＝役目を終えた、とは限りません（基本的な法律ほど安定していることもあります）。"
            "廃止・失効した法律は除いています。")
    R = [{"id": "stale", "tab": "放置年数", "title": "最後の改正から長くたっている法律",
          "desc": "一度改正されたあと、ずっと手が入っていない法律も含みます。", "rows": stale, "columns": cols, "method": meth,
          "trend": oc.trend(stale, "era", 100, "法律", "本"), "share_label": "law", "share_value": "years"},
         {"id": "never", "tab": "一度も改正なし", "title": "公布から一度も改正されていない法律",
          "desc": "制定されたままの姿で残っている法律。", "rows": never, "columns": cols2, "method": meth,
          "trend": oc.trend(never, "era", 100, "法律", "本"), "share_label": "law", "share_value": "age"},
         {"id": "era", "tab": "時代別", "title": "50年以上改正されていない法律の、制定された時代",
          "rows": by_era, "columns": [{"key": "era", "label": "公布された時代"}, {"key": "n", "label": "本数", "type": "num", "bar": True}],
          "method": meth, "share_label": "era", "share_value": "n"}]
    meta = {"data_period": "現行法令（%s時点）" % TODAY.isoformat(),
            "stats": [{"label": "数えた現行の法律", "value": len(rows), "unit": "本"},
                      {"label": "30年以上改正なし", "value": sum(1 for r in rows if r["years"] >= 30), "unit": "本"},
                      {"label": "一度も改正なし", "value": len(never), "unit": "本"}],
            "sources": [{"name": "e-Gov法令検索・法令API（Version 2）", "org": "デジタル庁", "url": PAGE, "license": "政府標準利用規約（第2.0版）"}]}
    oc.write(meta, R, search=[{"n": r["law"], "s": r["num"], "u": r["law_url"],
                            "k": [["最後の改正", r["last"]], ["放置年数", "%.1f年" % r["years"]]]} for r in rows])


if __name__ == "__main__":
    oc.main(run)
