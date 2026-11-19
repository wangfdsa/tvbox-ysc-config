#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知名 TVBox 源聚合 - GitHub Actions 更新脚本
- 读 config/sources.json，对每个源的多地址逐个尝试
- 识别真伪：有效 JSON(sites/urls/storeHouse) / 文本列表 / 图片反爬 / HTML / 失效
- 生成：多仓订阅、单仓聚合、每个源单独文件、状态报告、README 状态表、shields 徽章
- 容错：某源本次失败时沿用上次成功缓存（output/cache）
"""
import os, sys, json, re, time
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
    from requests.adapters import HTTPAdapter
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根
CONFIG = os.path.join(BASE, "config", "sources.json")
OUTPUT = os.path.join(BASE, "output")
CACHE = os.path.join(OUTPUT, "cache")
REPO = os.environ.get("GITHUB_REPOSITORY", "wangfdsa/tvbox-ysc-config")
# 订阅地址套 gh-proxy 加速前缀，国内机顶盒直连更稳；同时保留 raw 原址可选
RAW = f"https://gh-proxy.org/https://raw.githubusercontent.com/{REPO}/main/output"
RAW_DIRECT = f"https://raw.githubusercontent.com/{REPO}/main/output"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
TIMEOUT = 15
MAX_WORKERS = 8

# 成人内容过滤（高置信度词，避免自动混入黄色站）
FILTER_ADULT = True
ADULT_NAME = ["黄av","黄人","成人","色猫","色播","色情","性爱","湿妹","抖阴","souav","jav","18+","🔞","萝莉","麻豆","白嫖","番号","福利姬","偷拍","丝袜","美腿","人妻","熟女","御姐","乱伦","女优","porn","redtube","pornhub","missav","18av","sukebei","小黄书","涩涩","jable","netflav","youav","hanime","淫","艳","骚"]
ADULT_HOST = ["souav","sex","porn","jav","xvideos","xnxx","18av","caijiav","avzy"]

# 用户明确要求移除的源名（含多仓源内部展开的同名子订阅），命中即剔除
REMOVE_NAMES = ["集多","吃猫的鱼","少儿频道","戏曲音乐","小虎斑","夜猫子","传说","神秘的哥哥们",
                "环宇轩","影视仓","天微多仓","道长","吾爱","星辰","元兴","春盈天下","巧技","OK猫","OK吊炸天"]


def is_removed(name=""):
    n = str(name or "")
    return any(k in n for k in REMOVE_NAMES)


def is_adult(name="", api=""):
    if not FILTER_ADULT:
        return False
    n, u = str(name or "").lower(), str(api or "").lower()
    return any(k in n for k in ADULT_NAME) or any(k in u for k in ADULT_HOST)


def to_puny(url):
    m = re.match(r"^(https?://)([^/:]+)(.*)$", url)
    if not m:
        return url
    host = m.group(2)
    if any(ord(c) > 127 for c in host):
        try:
            host = host.encode("idna").decode("ascii")
        except Exception:
            pass
    return m.group(1) + host + m.group(3)


def strip_comments(text):
    return "\n".join(l for l in text.splitlines() if not l.strip().startswith("//"))


def fetch(url):
    """返回 (content_bytes, status_code, content_type) 或 (None, err_str, None)"""
    target = to_puny(url)
    headers = {"User-Agent": UA, "Accept": "*/*"}
    try:
        if HAS_REQUESTS:
            s = requests.Session()
            r = s.get(target, headers=headers, timeout=TIMEOUT, allow_redirects=True, verify=False)
            return r.content, r.status_code, r.headers.get("Content-Type", "")
        else:
            req = urllib.request.Request(target, headers=headers)
            r = urllib.request.urlopen(req, timeout=TIMEOUT)
            return r.read(), r.status, r.headers.get("Content-Type", "")
    except Exception as ex:
        return None, ("ERR " + str(ex)[:80]), None


def _fix_json_controls(s):
    """把 JSON 字符串内部未转义的裸换行/制表符替换为空格（如 '优\n酷'）。"""
    def repl(m):
        inner = m.group(1)
        inner = inner.replace("\r", " ").replace("\n", " ").replace("\t", " ")
        inner = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", inner)
        return '"' + inner + '"'
    return re.sub(r'"((?:[^"\\]|\\.)*)"', repl, s, flags=re.S)


def classify(body):
    """返回 (kind, data)。kind: single / multi / text / image / html / empty / bad"""
    if body is None or len(body) < 5:
        return "empty", None
    if body[:2] == b"\xff\xd8" or body[2:6] == b"JFIF" or body[:8] == b"\x89PNG\r\n\x1a\n" or body[:6] in (b"GIF87a", b"GIF89a"):
        return "image", None
    text = body.decode("utf-8", "ignore")
    cleaned = strip_comments(text).lstrip("\ufeff \n\r\t")
    if cleaned.startswith("{"):
        js = None
        for candidate in (cleaned, _fix_json_controls(cleaned)):
            try:
                js, _ = json.JSONDecoder().raw_decode(candidate)
                break
            except Exception:
                pass
        if isinstance(js, dict) and js:
            for mk in ("urls", "storeHouse"):
                if isinstance(js.get(mk), list):
                    return "multi", js
            if isinstance(js.get("sites"), list):
                return "single", js
            return "single", js
        return "bad", None
    if cleaned[:4].lower() in ("http", "#ext", "#extm3u"):
        return "text", text
    if "<html" in cleaned[:500].lower() or "<!doctype" in cleaned[:500].lower():
        return "html", None
    if "<html" in cleaned[:5000].lower() or "<div" in cleaned[:2000].lower():
        p = cleaned.find("{")
        if p >= 0:
            try:
                js, _ = json.JSONDecoder().raw_decode(cleaned[p:])
                if isinstance(js, dict) and js.get("sites"):
                    return "single", js
            except Exception:
                pass
    return "bad", None


def multi_items(data):
    """兼容 urls:[{name,url}] 与 storeHouse:[{sourceName,sourceUrl}] 两种多仓结构。"""
    if not isinstance(data, dict):
        return []
    for key in ("urls", "storeHouse"):
        arr = data.get(key)
        if isinstance(arr, list):
            out = []
            for x in arr:
                if isinstance(x, dict):
                    nm = x.get("name") or x.get("sourceName") or ""
                    ul = x.get("url") or x.get("sourceUrl") or ""
                    out.append((nm, ul))
                elif isinstance(x, str) and x.startswith("http"):
                    out.append(("", x))
            return out
    return []


def count_sites(kind, data):
    if kind == "single" and isinstance(data, dict):
        return len(data.get("sites", []))
    if kind == "multi":
        return len(multi_items(data))
    if kind == "text":
        return -1
    return 0


def fetch_source(src):
    name, sid = src["name"], src["id"]
    attempts = []
    for url in src.get("urls", []):
        t0 = time.time()
        body, code, ctype = fetch(url)
        ms = int((time.time() - t0) * 1000)
        if body is None:
            attempts.append({"url": url, "code": "ERR", "kind": "err", "ms": ms, "note": str(code)[:60]})
            continue
        kind, data = classify(body)
        attempts.append({"url": url, "code": str(code), "ctype": str(ctype)[:24],
                         "size": len(body), "kind": kind, "ms": ms})
        if kind in ("single", "multi", "text"):
            return {"id": sid, "name": name, "ok": True, "kind": kind, "data": data,
                    "raw_len": len(body), "ms": ms, "used_url": url, "attempts": attempts}
    return {"id": sid, "name": name, "ok": False, "attempts": attempts}


def load_cache(sid):
    p = os.path.join(CACHE, sid + ".json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def save_cache(sid, result):
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, sid + ".json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def localize_single(data, src_name):
    """把单仓里每个站点加上来源前缀、过滤成人。"""
    if not isinstance(data, dict):
        return data
    out = dict(data)
    sites = []
    for site in data.get("sites", []):
        if not isinstance(site, dict):
            continue
        sn, api = site.get("name", ""), str(site.get("api", ""))
        if is_adult(sn, api):
            continue
        s = dict(site)
        s["name"] = f"[{src_name}] {sn}"
        sites.append(s)
    out["sites"] = sites
    return out


def main():
    os.makedirs(OUTPUT, exist_ok=True)
    os.makedirs(os.path.join(OUTPUT, "sources"), exist_ok=True)
    cfg = json.load(open(CONFIG, encoding="utf-8"))
    sources = [s for s in cfg["sources"] if s.get("enabled", True)]
    print(f"[{datetime.now()}] 开始抓取 {len(sources)} 个源 (repo={REPO})", flush=True)

    results = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(fetch_source, s): s for s in sources}
        for f in as_completed(futs):
            r = f.result()
            results[r["id"]] = r

    status_list, live_single, multi_urls = [], [], []
    for s in sources:
        sid, name = s["id"], s["name"]
        r = results.get(sid, {"ok": False, "attempts": []})
        cached = False
        if not r["ok"]:
            c = load_cache(sid)
            if c and c.get("ok"):
                r = dict(c)
                r["from_cache"] = True
                cached = True
        if r.get("ok"):
            if not cached:
                save_cache(sid, r)
            cnt = count_sites(r["kind"], r["data"])
            status_list.append({"id": sid, "name": name, "status": "ok", "kind": r["kind"],
                                "sites": cnt, "ms": r.get("ms", -1), "used": r.get("used_url", ""),
                                "from_cache": cached, "attempts": r["attempts"]})
            # 单独源文件
            write_json(os.path.join(OUTPUT, "sources", sid + ".json"), r["data"])
            if r["kind"] == "single" and isinstance(r["data"], dict):
                for site in r["data"].get("sites", []):
                    if not isinstance(site, dict):
                        continue
                    sn, api = site.get("name", ""), str(site.get("api", ""))
                    if is_adult(sn, api):
                        continue
                    s2 = dict(site)
                    s2["name"] = f"[{name}] {sn}"
                    live_single.append(s2)
            elif r["kind"] == "multi":
                for sub_name, sub_url in multi_items(r["data"]):
                    if sub_url and is_adult(sub_name, sub_url):
                        continue
                    if sub_name and is_removed(sub_name):
                        continue
                    if sub_url:
                        multi_urls.append({"name": f"{name}-{sub_name}"[:30], "url": sub_url})
            # 单仓源：多仓订阅指向本仓库的单源文件（配合缓存容错，上游挂了仍可用）
            if r["kind"] == "single" and r.get("used_url"):
                multi_urls.append({"name": name, "url": f"{RAW}/sources/{sid}.json"})
        else:
            status_list.append({"id": sid, "name": name, "status": "fail", "attempts": r.get("attempts", [])})

    # 单仓聚合去重
    seen, dedup = set(), []
    for site in live_single:
        key = str(site.get("key", "")) + "|" + str(site.get("api", ""))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(site)

    now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    write_json(os.path.join(OUTPUT, "多仓订阅.json"), {"urls": multi_urls})
    write_json(os.path.join(OUTPUT, "单仓聚合.json"), {"sites": dedup})

    ok_cnt = sum(1 for s in status_list if s["status"] == "ok")
    status = {"updated": now, "total": len(sources), "ok": ok_cnt,
              "fail": len(sources) - ok_cnt, "merged_sites": len(dedup),
              "filter_adult": FILTER_ADULT, "sources": status_list}
    write_json(os.path.join(OUTPUT, "status.json"), status)
    # shields 徽章
    write_json(os.path.join(OUTPUT, "shield.json"), {
        "schemaVersion": 1, "label": "可用源",
        "message": f"{ok_cnt}/{len(sources)}",
        "color": "brightgreen" if ok_cnt >= len(sources) * 0.6 else ("yellow" if ok_cnt >= 5 else "red")
    })

    gen_readme(status, multi_urls, dedup, now)
    print(f"完成：{ok_cnt}/{len(sources)} 源可用，聚合 {len(dedup)} 站点", flush=True)
    for s in status_list:
        mark = "OK " if s["status"] == "ok" else "X  "
        extra = f"{s.get('sites','')}站 {s.get('ms','')}ms" if s["status"] == "ok" else ""
        print(f"  {mark}{s['name']:<14} {extra}", flush=True)


def gen_readme(status, multi_urls, dedup, now):
    rows = []
    for s in status["sources"]:
        if s["status"] == "ok":
            badge = "✅ 成功" + ("（缓存）" if s.get("from_cache") else "")
            detail = f"{s.get('sites','')} 站 · {s.get('ms','')}ms"
        else:
            badge, detail = "❌ 失败", "全部地址尝试失败"
        rows.append(f"| {s['name']} | {badge} | {detail} |")
    sources_md = "\n".join(rows)
    multi_url = f"{RAW}/多仓订阅.json"
    all_url = f"{RAW}/单仓聚合.json"
    md = f"""# 影视仓 / TVBox 配置聚合（GitHub Actions 版）

![配置状态](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2F{REPO}%2Fmain%2Foutput%2Fshield.json)
![更新频率](https://img.shields.io/badge/%E6%9B%B4%E6%96%B0-%E6%AF%8F%E5%A4%A9%202%20%E6%AC%A1-blue)

聚合 40+ 个知名 TVBox / 影视仓接口，通过 **GitHub Actions 云端定时自动更新**，结果提交回本仓库。已开启成人内容过滤、缓存容错、中文域名 punycode 兼容。

> 所有配置来自互联网公开分享，版权归原作者所有；本仓库仅做聚合与镜像，仅供学习交流，请勿商用。

---

## 一、订阅地址（填进 TVBox / 影视仓）

| 类型 | 地址 |
| --- | --- |
| **多仓订阅（推荐）** | `{multi_url}` |
| **单仓聚合（所有站点合并）** | `{all_url}` |
| 运行状态 | `{RAW}/status.json` |
| 单独源 | `{RAW}/sources/源ID.json` |

> 国内直连 `raw.githubusercontent.com` 若慢，可套加速前缀，如 `https://gh-proxy.com/` + 上面的完整地址。

---

## 二、源可用性状态

<!-- STATUS_START -->
> 🔄 最近更新：{now}（北京时间） · 成功 **{status['ok']}/{status['total']}** 个源 · 聚合 {len(dedup)} 站点

| 配置源 | 状态 | 详情 |
| --- | --- | --- |
{sources_md}
<!-- STATUS_END -->

---

## 三、自动更新机制

- `.github/workflows/update.yml` 每天 **02:00 / 14:00 UTC**（北京 10:00 / 22:00）自动运行。
- 也可在 **Actions → Auto Update → Run workflow** 手动触发。
- 用内置 `GITHUB_TOKEN` 自动提交 `output/`，无需任何密钥。
- push 只监听 `config/`、`scripts/`，自动提交 `output/` 不会死循环。

## 四、自定义源

编辑 `config/sources.json`，每个源格式：

```json
{{"id": "mysource", "name": "我的源", "enabled": true, "urls": ["主地址", "备用地址"]}}
```

推送后自动触发更新。失效源会保留记录，恢复后自动启用。
"""
    with open(os.path.join(BASE, "README.md"), "w", encoding="utf-8") as f:
        f.write(md)


if __name__ == "__main__":
    main()
