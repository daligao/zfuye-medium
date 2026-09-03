#!/usr/bin/env python3
"""
zfuye-medium: Medium/Entrepreneur精品文章 → 全程走Webshare代理 → 翻译 → zfuye.org发布
"""

import os, json, random, datetime, requests, re
import xml.etree.ElementTree as ET
from html import unescape
from base64 import b64encode
from urllib.parse import urlparse

DEEPSEEK_KEY  = os.environ.get("DEEPSEEK_KEY", "")
ALIYUN_KEY    = os.environ.get("ALIYUN_KEY", "")
ALIYUN_BASE   = "https://llm-8yhqvemunmnpoeoj.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
WP_USER       = os.environ.get("WP_USER", "")
WP_APP_PASS   = os.environ.get("WP_APP_PASS", "")
WEBSHARE_USER = os.environ.get("WEBSHARE_USER", "")
WEBSHARE_PASS = os.environ.get("WEBSHARE_PASS", "")
WP_BASE       = "https://www.zfuye.org/wp-json/wp/v2"

TODAY    = datetime.date.today().isoformat()
HOUR_U   = datetime.datetime.utcnow().hour
LOG_PATH = "data/log.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

FAIL_PHRASES = ["未能取得", "无法逐句", "正文内容缺失", "未能获取", "无法翻译", "抓取失败"]

# ── 数据源（全部软付费墙精品源）────────────────────────────────────────────────
SOURCES = [
    # Medium 高质量标签
    {"name": "Medium·副业",       "cat": "AI副业",   "url": "https://medium.com/feed/tag/side-hustle"},
    {"name": "Medium·创业",       "cat": "海外接单", "url": "https://medium.com/feed/tag/entrepreneurship"},
    {"name": "Medium·被动收入",   "cat": "被动收入", "url": "https://medium.com/feed/tag/passive-income"},
    {"name": "Medium·自由职业",   "cat": "海外接单", "url": "https://medium.com/feed/tag/freelancing"},
    {"name": "Medium·赚钱",       "cat": "信息差",   "url": "https://medium.com/feed/tag/make-money-online"},
    {"name": "Medium·AI工具",     "cat": "AI副业",   "url": "https://medium.com/feed/tag/artificial-intelligence"},
    {"name": "Medium·个人理财",   "cat": "被动收入", "url": "https://medium.com/feed/tag/personal-finance"},
    # Entrepreneur 全站
    {"name": "Entrepreneur",      "cat": "海外接单", "url": "https://www.entrepreneur.com/latest.rss"},
    {"name": "Entrepreneur·副业", "cat": "AI副业",   "url": "https://www.entrepreneur.com/topic/side-hustle.rss"},
    {"name": "Inc.com",           "cat": "信息差",   "url": "https://www.inc.com/rss"},
]

ALL_CATS = ["AI副业", "海外接单", "信息差", "被动收入"]


# ── 代理抓取（直接用curl，绕过Python的HTTPS隧道认证bug）─────────────────────
import subprocess

def proxy_get(url):
    """用curl走Webshare代理抓页面，返回HTML文本"""
    if WEBSHARE_USER:
        cmd = ["curl", "-s", "-L", "--max-time", "20",
               "--proxy", f"http://{WEBSHARE_USER}:{WEBSHARE_PASS}@p.webshare.io:80/",
               "-A", HEADERS["User-Agent"], url]
    else:
        cmd = ["curl", "-s", "-L", "--max-time", "20", "-A", HEADERS["User-Agent"], url]
    result = subprocess.run(cmd, capture_output=True, timeout=25)
    return result.stdout.decode("utf-8", errors="replace")


# ── 日志 ─────────────────────────────────────────────────────────────────────
def load_log():
    try:
        with open(LOG_PATH) as f: return json.load(f)
    except: return {"used_urls": [], "published": []}

def save_log(log):
    os.makedirs("data", exist_ok=True)
    with open(LOG_PATH, "w") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


# ── 抓取 ──────────────────────────────────────────────────────────────────────
def fetch_rss(source):
    try:
        r = requests.get(source["url"], headers=HEADERS, timeout=15)  # RSS不需要代理
        root = ET.fromstring(r.content)
        items = root.findall(".//item")
        results = []
        for item in items[:10]:
            title = item.find("title")
            link  = item.find("link")
            desc  = item.find("description")
            if title is None or link is None: continue
            t = unescape((title.text or "").strip())
            l = (link.text or "").strip()
            d = unescape(re.sub(r'<[^>]+>', '', (desc.text or "") if desc is not None else "")[:400]).strip()
            if t and l:
                results.append({"title": t, "url": l, "summary": d, "source": source["name"], "cat": source["cat"]})
        return results
    except Exception as e:
        print(f"  [{source['name']}] RSS失败: {e}")
        return []


def fetch_full_text(url, max_chars=5000):
    return ""  # Medium/Entrepreneur是SPA，HTML里无正文，用RSS摘要+DeepSeek写作替代


# ── 选文章 ────────────────────────────────────────────────────────────────────
def pick_article(log):
    used = set(log.get("used_urls", []))
    today_counts = {}
    for p in log.get("published", []):
        if isinstance(p, dict) and p.get("date") == TODAY:
            today_counts[p.get("cat", "")] = today_counts.get(p.get("cat",""), 0) + 1

    sorted_cats = sorted(ALL_CATS, key=lambda c: today_counts.get(c, 0))
    for cat in sorted_cats:
        sources = [s for s in SOURCES if s["cat"] == cat]
        random.shuffle(sources)
        for src in sources:
            articles = fetch_rss(src)
            fresh = [a for a in articles if a["url"] not in used]
            if fresh:
                return random.choice(fresh[:4])

    for src in random.sample(SOURCES, len(SOURCES)):
        articles = fetch_rss(src)
        fresh = [a for a in articles if a["url"] not in used]
        if fresh:
            return fresh[0]
    return None


# ── DeepSeek写作 ──────────────────────────────────────────────────────────────
def write_from_source(article, body):
    summary = body or article.get("summary", "")
    prompt = f"""以下是一篇海外文章的标题和摘要：
标题：{article['title']}
来源：{article['source']}
摘要：{summary}
原文链接：{article['url']}

【重要】请先判断这篇文章是否适合发布：
- 如果内容涉及政治、军事、地缘冲突、政府批评、敏感社会议题，请直接回复"SKIP"
- 只发布科技、商业、副业、赚钱、工具、创业类内容

如果内容合适，请做三件事：
1. 根据标题和摘要，结合你的知识，用中文写一篇800-1200字的深度解读文章（不是翻译，而是把这个话题讲透，加入实际方法和案例）
2. 文末加编者点评（2-3句你的看法）
3. 最后加3个FAQ问答，用中国读者会搜索的问题：

<h2>常见问题</h2>
<h3>Q：[问题]</h3>
<p>A：[回答，2-3句]</p>
（重复3次）

格式要求：
- HTML格式，用<h2><p><ul><li>
- 不要写文章大标题
- 不要```html代码块标记
- 编者按：<blockquote style="border-left:3px solid #f0a500;padding:12px 16px;margin:24px 0;background:#fffbf0;color:#555">[点评]</blockquote>
- 结尾：<p style="color:#999;font-size:13px">资讯来源：{article['source']}</p>"""

    try:
        r = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
            json={"model": "deepseek-v4-flash",
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.7},
            timeout=90,
        )
        content = r.json()["choices"][0]["message"]["content"].strip()
        if content.strip().upper().startswith("SKIP"):
            print("  [DeepSeek] 内容不合规，跳过")
            return None
        if any(p in content for p in FAIL_PHRASES):
            print("  [DeepSeek] 内容无效，跳过")
            return None
        print(f"  [DeepSeek] 完成 {len(content)} 字")
        return content
    except Exception as e:
        print(f"  [DeepSeek] 失败: {e}")
        return None


def gen_cn_title(article):
    try:
        r = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
            json={"model": "deepseek-v4-flash",
                  "messages": [{"role": "user", "content":
                      f"""把英文标题改写成中文搜索词风格标题：
- 用中国人搜索框会输入的词
- 带数字（金额/时间/步骤）优先
- 10-18字，口语化
- 人名换成"一位美国人""一个创业者"等
- 例子："月入5万的副业怎么做""3步建自动赚钱网站"
只输出标题，不加引号

英文标题：{article['title']}"""}],
                  "temperature": 0.6},
            timeout=60,
        )
        title = r.json()["choices"][0]["message"]["content"].strip()
        if sum(1 for c in title if '一' <= c <= '鿿') < 3:
            raise ValueError("非中文")
        print(f"  [标题] {title}")
        return title
    except Exception as e:
        print(f"  [标题] 失败({e})，用原标题")
        return article["title"]


# ── 阿里云生成 meta description ───────────────────────────────────────────────
def gen_excerpt(title_cn, content):
    plain = re.sub(r'<[^>]+>', '', content)[:400].strip()
    if not ALIYUN_KEY:
        return plain[:80]
    try:
        r = requests.post(
            f"{ALIYUN_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {ALIYUN_KEY}", "Content-Type": "application/json"},
            json={"model": "qwen-turbo",
                  "messages": [{"role": "user", "content":
                      f"根据以下文章标题和开头，写一句60-80字的中文SEO摘要，吸引点击，不加引号，直接输出：\n标题：{title_cn}\n内容：{plain}"}],
                  "max_tokens": 120, "temperature": 0.5},
            timeout=20,
        )
        excerpt = r.json()["choices"][0]["message"]["content"].strip()
        print(f"  [摘要] {excerpt[:50]}…")
        return excerpt
    except Exception as e:
        print(f"  [摘要] 阿里云失败({e})，用纯文本截取")
        return plain[:80]


# ── WordPress发布 ─────────────────────────────────────────────────────────────
def get_or_create_category(name, auth_h):
    try:
        r = requests.get(f"{WP_BASE}/categories?search={name}&per_page=5", headers=auth_h, timeout=10)
        for c in r.json():
            if c["name"] == name: return c["id"]
        r2 = requests.post(f"{WP_BASE}/categories",
                           headers={**auth_h, "Content-Type": "application/json"},
                           json={"name": name}, timeout=10)
        return r2.json().get("id")
    except: return None


def get_related_posts(cat_name, exclude_id, auth_h):
    try:
        r = requests.get(f"{WP_BASE}/categories?search={cat_name}&per_page=5", headers=auth_h, timeout=8)
        cats = [c for c in r.json() if c["name"] == cat_name]
        if not cats: return ""
        r2 = requests.get(
            f"{WP_BASE}/posts?categories={cats[0]['id']}&exclude={exclude_id}&per_page=3&orderby=date&order=desc",
            headers=auth_h, timeout=8)
        posts = r2.json()
        if not posts: return ""
        items = "".join(f'<li><a href="{p["link"]}">{p["title"]["rendered"]}</a></li>' for p in posts)
        return f"""
<hr style="margin:32px 0 16px;border:none;border-top:1px solid #eee">
<div style="background:#f5f5f5;border-radius:8px;padding:16px 20px;font-size:14px">
  <p style="margin:0 0 10px;font-weight:bold;color:#333">📖 相关阅读</p>
  <ul style="margin:0;padding-left:18px;line-height:2;color:#555">{items}</ul>
</div>"""
    except: return ""


def build_faq_schema(content, title):
    import json as _j
    qs = re.findall(r'<h3>Q[：:]\s*(.+?)</h3>\s*<p>A[：:]\s*(.+?)</p>', content, re.S)
    if not qs: return ""
    entities = [{"@type": "Question", "name": q.strip(),
                 "acceptedAnswer": {"@type": "Answer", "text": re.sub(r'<[^>]+>', '', a).strip()}}
                for q, a in qs[:5]]
    schema = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": entities}
    return f'\n<script type="application/ld+json">{_j.dumps(schema, ensure_ascii=False)}</script>\n'


AD_FOOTER = """
<hr style="margin:40px 0 24px;border:none;border-top:1px solid #eee">
<div style="border:2px solid #f0a500;border-radius:10px;background:#fffbf0;padding:20px 24px;font-size:14px;line-height:1.9">
  <p style="margin:0 0 4px;font-size:13px;color:#c47f00;font-weight:bold;letter-spacing:1px">🏷️ 限时推荐</p>
  <p style="margin:0 0 12px;font-weight:bold;font-size:16px;color:#333">📌 关于本站</p>
  <p style="margin:0 0 14px;color:#555">内容翻译自海外科技媒体，仅供个人学习参考。</p>
  <p style="margin:0 0 8px;font-weight:bold;color:#333">🛠️ 站长的同款工具</p>
  <ul style="margin:0 0 16px;padding-left:20px;color:#555">
    <li>主机：<a href="https://zfuye.org/3528.html" target="_blank" rel="nofollow" style="color:#c47f00;font-weight:bold">Hostinger</a>（$2.99/月起）</li>
    <li>域名：<a href="https://www.namecheap.com" target="_blank" rel="nofollow" style="color:#c47f00;font-weight:bold">Namecheap</a></li>
    <li>AI工具：GitHub Copilot（<a href="https://zfuye.org/3528.html" target="_blank" rel="nofollow" style="color:#c47f00;font-weight:bold">操作方法：在这里</a>）</li>
  </ul>
  <p style="margin:0;color:#c47f00;font-weight:bold">你也可以做一台自动赚钱的网站机器 🚀</p>
</div>"""


def publish_post(title_cn, raw_content, article, excerpt=""):
    cred   = b64encode(f"{WP_USER}:{WP_APP_PASS}".encode()).decode()
    auth_h = {"Authorization": f"Basic {cred}"}
    cat_id = get_or_create_category(article["cat"], auth_h)
    payload = {"title": {"raw": title_cn}, "content": {"raw": raw_content},
               "excerpt": {"raw": excerpt}, "status": "publish", "format": "standard"}
    if cat_id:
        payload["categories"] = [cat_id]
    try:
        r = requests.post(f"{WP_BASE}/posts",
                          headers={**auth_h, "Content-Type": "application/json"},
                          json=payload, timeout=20)
        data = r.json()
        if "id" in data:
            print(f"  ✅ 发布成功: {data['link']}")
            return data["id"], data["link"]
        print(f"  ❌ 发布失败: {data}")
        return None, None
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        return None, None


def update_post(post_id, raw_content):
    cred   = b64encode(f"{WP_USER}:{WP_APP_PASS}".encode()).decode()
    auth_h = {"Authorization": f"Basic {cred}", "Content-Type": "application/json"}
    try:
        requests.post(f"{WP_BASE}/posts/{post_id}", headers=auth_h,
                      json={"content": {"raw": raw_content}}, timeout=20)
    except: pass


# ── WP连通性检查（先验证，避免DeepSeek白调）─────────────────────────────────
def check_wp_auth():
    cred = b64encode(f"{WP_USER}:{WP_APP_PASS}".encode()).decode()
    try:
        r = requests.get(f"{WP_BASE}/users/me",
                         headers={"Authorization": f"Basic {cred}"}, timeout=10)
        if r.status_code == 200:
            return True
        print(f"  [WP] 认证失败 {r.status_code}，跳过本次（避免浪费DeepSeek token）")
        return False
    except Exception as e:
        print(f"  [WP] 连接失败: {e}，跳过本次")
        return False


# ── 主流程 ────────────────────────────────────────────────────────────────────
def main():
    print(f"📰 zfuye-medium — {TODAY} UTC+{HOUR_U}h")
    log = load_log()

    if not check_wp_auth():
        return

    article = pick_article(log)
    if not article:
        print("  ⚠️ 没有新文章，跳过")
        return

    print(f"  来源: {article['source']} [{article['cat']}]")
    print(f"  原标题: {article['title'][:70]}")

    summary = article.get("summary", "")
    print(f"  [摘要] {len(summary)} 字符")
    if len(summary) < 30:
        print("  ⚠️ 摘要太短，跳过")
        log.setdefault("used_urls", []).append(article["url"])
        save_log(log)
        return

    title_cn = gen_cn_title(article)
    content  = write_from_source(article, "")
    if not content or len(content) < 300:
        print("  ⚠️ 内容不合规或过短，跳过")
        log.setdefault("used_urls", []).append(article["url"])
        save_log(log)
        return

    content += AD_FOOTER
    excerpt  = gen_excerpt(title_cn, content)
    post_id, link = publish_post(title_cn, content, article, excerpt)

    if post_id and link:
        cred   = b64encode(f"{WP_USER}:{WP_APP_PASS}".encode()).decode()
        auth_h = {"Authorization": f"Basic {cred}"}
        related    = get_related_posts(article["cat"], post_id, auth_h)
        faq_schema = build_faq_schema(content, title_cn)
        if related or faq_schema:
            update_post(post_id, content + faq_schema + related)

    if link:
        log.setdefault("used_urls", []).append(article["url"])
        log.setdefault("published", []).append(
            {"date": TODAY, "title": title_cn, "source": article["source"], "url": link})
        if len(log["used_urls"]) > 500:
            log["used_urls"] = log["used_urls"][-500:]
        save_log(log)

    print("✅ 完成")


if __name__ == "__main__":
    main()

