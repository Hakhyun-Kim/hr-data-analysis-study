"""해외 채용 트렌드 수집 — Hacker News 'Ask HN: Who is hiring?' 월별 스레드.

국내 데이터의 가장 큰 공백은 **시계열**이다. 국내 채용 플랫폼 JD는 현재 단면만 받을 수 있고,
워크넷·EIS는 접근이 막혔다. HN 월간 채용 스레드는 2011년부터 매달 열려 있어
동일 형식의 채용글을 월 단위로 비교할 수 있다. 인증키가 필요 없다.

수집 구조
  1) Algolia API로 author_whoishiring 의 월별 story 목록 수집
  2) 각 story 의 최상위 댓글(=개별 채용 공고) 수집
  3) 월 × 기술 키워드 문서빈도(등장 공고 수) 집계

실행 예시:
  python src/collect_global_hn.py --start 202001
"""

import argparse
import html
import os
import re
import sys
import time

import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from provenance import DATA_DIR, record, save_raw  # noqa: E402

SEARCH_URL = "https://hn.algolia.com/api/v1/search"
TIMEOUT = 40

# 국내 분석과 동일한 스택 사전을 쓰되, 해외에서 통용되는 표기를 보강한다.
AI_STACK = ["LLM", "RAG", "Agent", "LangChain", "LlamaIndex", "Fine-tuning",
            "Vector DB", "embedding", "prompt", "GenAI", "OpenAI", "PyTorch"]
CLASSIC_STACK = ["Spring", "Java", "MySQL", "Kubernetes", "Docker", "AWS",
                 "Django", "Node.js", "Rails", "Postgres"]
ALL_STACK = AI_STACK + CLASSIC_STACK


def mentions(text: str, keyword: str) -> bool:
    if keyword.isascii():
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(keyword)}(?![A-Za-z0-9])",
                         text, re.IGNORECASE) is not None
    return keyword in text


def clean(raw: str) -> str:
    """HN 댓글은 HTML 조각이다. 태그를 지우고 엔티티를 되돌린다."""
    return html.unescape(re.sub(r"<[^>]+>", " ", raw or ""))


def fetch_threads(session: requests.Session, start: str) -> list[dict]:
    """월별 'Who is hiring?' 스토리 목록. start 이후만 남긴다."""
    threads, page = [], 0
    while True:
        resp = session.get(SEARCH_URL, params={
            "tags": "story,author_whoishiring",
            "hitsPerPage": 100,
            "page": page,
        }, timeout=TIMEOUT)
        if resp.status_code != 200:
            raise SystemExit(f"\n[중단] HN story 목록 실패: HTTP {resp.status_code}\n")

        payload = resp.json()
        for hit in payload.get("hits", []):
            title = hit.get("title") or ""
            if "who is hiring" not in title.lower():
                continue  # 'Who wants to be hired', 'Freelancer' 스레드 제외
            ym = (hit.get("created_at") or "")[:7].replace("-", "")
            if ym and ym >= start:
                threads.append({"id": hit["objectID"], "ym": ym, "title": title,
                                "num_comments": hit.get("num_comments") or 0})

        page += 1
        if page >= payload.get("nbPages", 0):
            break
        time.sleep(0.2)

    return sorted({t["id"]: t for t in threads}.values(), key=lambda t: t["ym"])


def fetch_posts(session: requests.Session, story_id: str) -> list[str]:
    """스레드의 최상위 댓글 = 개별 채용 공고 본문."""
    resp = session.get(SEARCH_URL, params={
        "tags": f"comment,story_{story_id}",
        "hitsPerPage": 1000,
    }, timeout=TIMEOUT)
    if resp.status_code != 200:
        return []

    posts = []
    for hit in resp.json().get("hits", []):
        text = clean(hit.get("comment_text"))
        # 최상위 댓글만 채용 공고다. 대댓글(질문/잡담)은 parent_id 가 story 가 아니다.
        if str(hit.get("parent_id")) != str(story_id):
            continue
        if len(text.strip()) < 80:  # 한 줄짜리 잡담 제외
            continue
        posts.append(text)
    return posts


def main() -> None:
    parser = argparse.ArgumentParser(description="HN 월간 채용 스레드 수집")
    parser.add_argument("--start", default="202001", help="수집 시작 YYYYMM")
    args = parser.parse_args()

    session = requests.Session()
    session.headers["User-Agent"] = "hr-data-analysis-study/1.0 (research)"

    print(f"HN 'Who is hiring?' 수집 시작 ({args.start} 이후)\n")
    threads = fetch_threads(session, args.start)
    if not threads:
        raise SystemExit("\n[중단] 대상 스레드 0건\n")
    print(f"대상 스레드 {len(threads)}개 ({threads[0]['ym']} ~ {threads[-1]['ym']})\n")

    # 한 달에 스레드가 두 개 열리는 경우가 있다(2020-03 실측: story 22465476 + 22665398).
    # 월을 키로 덮어쓰면 원본이 조용히 사라지고, 스레드마다 행을 만들면 그 달이 두 번 세어진다.
    # 월 단위로 합치고 story_id 는 목록으로 남긴다.
    raw_posts: dict[str, list[str]] = {}
    story_ids: dict[str, list[str]] = {}
    total_posts = 0
    for i, thread in enumerate(threads, 1):
        posts = fetch_posts(session, thread["id"])
        if not posts:
            print(f"  [경고] {thread['ym']} 공고 0건 (story {thread['id']})")
            continue

        ym = thread["ym"]
        if ym in raw_posts:
            print(f"  [주의] {ym} 스레드 2개 — 합산합니다 (story {thread['id']})")
        raw_posts.setdefault(ym, []).extend(posts)
        story_ids.setdefault(ym, []).append(str(thread["id"]))
        total_posts += len(posts)

        if i % 12 == 0:
            print(f"  {i}/{len(threads)} 스레드 처리 (누적 공고 {total_posts:,}건)")
        time.sleep(0.25)

    if not raw_posts:
        raise SystemExit("\n[중단] 수집된 공고가 0건\n")

    rows = []
    for ym, posts in sorted(raw_posts.items()):
        row = {"기준월": ym, "story_id": "|".join(story_ids[ym]), "공고수": len(posts)}
        for keyword in ALL_STACK:
            row[keyword] = sum(1 for p in posts if mentions(p, keyword))
        row["AI스택_1개이상"] = sum(1 for p in posts
                                if any(mentions(p, k) for k in AI_STACK))
        row["전통스택_1개이상"] = sum(1 for p in posts
                                 if any(mentions(p, k) for k in CLASSIC_STACK))
        rows.append(row)

    raw_path = save_raw("hn_hiring", raw_posts)
    df = pd.DataFrame(rows).sort_values("기준월")
    df["AI스택_비율"] = (df["AI스택_1개이상"] / df["공고수"]).round(4)
    df["전통스택_비율"] = (df["전통스택_1개이상"] / df["공고수"]).round(4)

    out = os.path.join(DATA_DIR, "global_hn_hiring.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")

    record("hn_whoishiring", SEARCH_URL,
           {"tags": "story,author_whoishiring", "start": args.start,
            "threads": len(threads)},
           200, int(df["공고수"].sum()), raw_path, ["data/global_hn_hiring.csv"],
           notes=f"{len(rows)}개월 / 인증키 불필요")

    print(f"\n[완료] {len(rows)}개월 / 채용글 {total_posts:,}건")
    print(f"  기간: {df['기준월'].iloc[0]} ~ {df['기준월'].iloc[-1]}")
    print(f"  원본: {raw_path}")
    print(f"  가공: data/global_hn_hiring.csv")


if __name__ == "__main__":
    main()
