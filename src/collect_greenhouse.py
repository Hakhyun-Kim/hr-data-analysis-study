"""해외 채용 JD 수집 — Greenhouse 채용 보드 공개 API.

HN 채용글의 한계는 **표본**이다. 'Who is hiring?' 스레드는 스타트업·원격·미국 중심이고,
본문 형식이 자유 텍스트라 직무·부서·근무지를 구조화된 값으로 받을 수 없다.

Greenhouse 는 기업이 자기 채용 페이지를 만들 때 쓰는 ATS 이고, 그 채용 보드는
**인증키 없이 공개 API 로 열려 있다.** 회사가 스스로 게시한 원문이므로
  · 부서(departments) / 근무지(offices) / 직무명이 구조화돼 있고
  · JD 본문 전체를 받을 수 있어 국내 JD 와 같은 방식으로 스택을 셀 수 있다.

주의 — 이 수집분으로 하면 안 되는 것
  `first_published` 필드가 있어 월별 집계가 가능해 보이지만, **현재 열려 있는 공고만**
  응답에 포함된다. 마감된 공고는 사라지므로 과거로 갈수록 표본이 줄어드는
  생존 편향이 생긴다. 따라서 이 데이터로 '채용 물량 추이'를 말할 수 없다.
  시계열은 HN(collect_global_hn.py) 쪽만 유효하다. 여기서는 단면 비교만 한다.

수집 원칙
  · 보드 하나라도 실패하면 저장하지 않고 중단한다. 일부 회사만 빠진 수집분은
    회사 구성이 달라져 국내 JD 와의 비교 기준이 흔들리기 때문이다.
    회사가 ATS 를 옮겨 보드가 사라진 경우에만 --skip-missing 으로 명시적으로 넘긴다.
  · 스택 사전과 매칭 규칙은 collect_global_hn 에서 가져다 쓴다. 사전이 갈라지면
    HN 수치와 Greenhouse 수치를 나란히 놓을 수 없다.

실행 예시:
  python src/collect_greenhouse.py
  python src/collect_greenhouse.py --boards stripe,figma --skip-missing
"""

import argparse
import json
import os
import re
import sys
import time

import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from collect_global_hn import AI_STACK, CLASSIC_STACK, clean, mentions  # noqa: E402
from provenance import DATA_DIR, record, save_raw  # noqa: E402

BASE = "https://boards-api.greenhouse.io/v1/boards"
TIMEOUT = 40

# 2026-08-11 실제 호출로 응답을 확인한 보드만 남겼다.
# 회사가 ATS 를 옮기면 예고 없이 404 가 되므로, 목록은 고정값이 아니라 검증 대상이다.
# (같은 날 openai / notion / snowflake / plaid / ramp 등은 404 였다 — Greenhouse 를 쓰지 않는다)
DEFAULT_BOARDS = [
    "affirm", "airtable", "anthropic", "asana", "brex", "chime", "cloudflare",
    "coinbase", "databricks", "datadog", "discord", "dropbox", "duolingo",
    "elastic", "figma", "flexport", "gitlab", "instacart", "lyft", "mongodb",
    "pinterest", "reddit", "robinhood", "samsara", "scaleai", "sofi", "stripe",
    "twilio", "vercel", "verkada", "webflow",
]

# 게임사는 위 목록에 없다. HN 채용글에서 게임 관련 언급이 연 16~92건뿐이라
# 게임 직군을 따로 보려면 별도 표본이 필요하다. 2026-08-11 응답을 확인한 보드만 넣었다.
# (bungie 는 2건뿐이라 제외 — unity / ea / blizzard / nexon 등은 Greenhouse 를 쓰지 않는다)
GAME_BOARDS = ["riotgames", "epicgames", "roblox", "scopely", "krafton"]

# 개발 직군 판정은 **부서명이 아니라 직무명**으로 한다.
# departments 는 회사마다 표기 체계가 달라 신뢰할 수 없다. 실제로 2026-08-11 수집분에서
# figma 는 'Engineering' 이라고 쓰지만 stripe 는 '8548 Payins - Eng', '8122 Data Foundations'
# 처럼 사내 코드가 붙은 팀명을 쓴다. 부서명으로 거르면 stripe 공고 대부분이 탈락한다.
# 직무명은 회사가 달라도 표기가 일정한 편이라 오탐/미탐이 모두 적다.
DEV_TITLE = re.compile(
    r"\b(engineer|engineering|developer|programmer|architec(t|ture)|scientist|"
    r"sre|devops|infrastructure|platform|full[- ]?stack|back[- ]?end|front[- ]?end|"
    r"machine learning|\bml\b|research (engineer|scientist)|data|security|"
    r"android|ios|mobile|qa)\b",
    re.IGNORECASE)

# 위 사전에 걸리지만 개발 직군이 아닌 것들. 'Sales Engineer', 'Data Center Technician',
# 'Security Guard' 처럼 같은 단어를 쓰는 비개발 직무를 좁게 지정해 제외한다.
NON_DEV_TITLE = re.compile(
    r"\b(sales|account executive|recruit|marketing|counsel|paralegal|"
    r"customer success|support specialist|technician|guard|facilities)\b",
    re.IGNORECASE)


def fetch_board(session: requests.Session, board: str) -> tuple[int, list[dict]]:
    """보드 하나의 전체 공고. content=true 여야 JD 본문이 함께 온다."""
    resp = session.get(f"{BASE}/{board}/jobs", params={"content": "true"},
                       timeout=TIMEOUT)
    if resp.status_code != 200:
        return resp.status_code, []
    return 200, resp.json().get("jobs", [])


def is_dev(job: dict) -> bool:
    title = job.get("title") or ""
    return bool(DEV_TITLE.search(title)) and not NON_DEV_TITLE.search(title)


def to_record(board: str, job: dict) -> dict:
    """분석 스크립트가 국내 JD 와 같은 방식으로 다룰 수 있게 구조를 맞춘다."""
    depts = [d.get("name") for d in job.get("departments") or [] if d.get("name")]
    offices = [o.get("name", "").strip() for o in job.get("offices") or [] if o.get("name")]
    return {
        "structured": {
            "job_id": job.get("id"),
            "board": board,
            "company_name": job.get("company_name") or board,
            "department": " / ".join(depts),
            "office": " / ".join(offices),
            "location": (job.get("location") or {}).get("name"),
            "first_published": job.get("first_published"),
            "updated_at": job.get("updated_at"),
            "url": job.get("absolute_url"),
        },
        "unstructured": {
            "position": job.get("title"),
            # content 는 HTML 엔티티가 이중 이스케이프된 문자열이다. HN 댓글과 같은
            # 정제 함수를 써서 태그를 지우고 엔티티를 되돌린다.
            "content": clean(job.get("content")),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Greenhouse 채용 보드 JD 수집")
    parser.add_argument("--boards", default="",
                        help=f"쉼표 구분 board token (기본: 검증된 {len(DEFAULT_BOARDS)}개)")
    parser.add_argument("--game", action="store_true",
                        help=f"게임사 {len(GAME_BOARDS)}곳만 수집 (별도 파일로 저장)")
    parser.add_argument("--tag", default="",
                        help="출력 파일명 접미사. 다른 모집단을 덮어쓰지 않기 위해 씁니다")
    parser.add_argument("--dev-only", action="store_true",
                        help="개발 관련 부서 공고만 남긴다")
    parser.add_argument("--skip-missing", action="store_true",
                        help="404 보드를 중단 대신 건너뛴다 (보드 구성 변경 시에만)")
    parser.add_argument("--sleep", type=float, default=0.3, help="요청 간 대기(초)")
    args = parser.parse_args()

    if args.boards:
        boards = [b.strip() for b in args.boards.split(",") if b.strip()]
    elif args.game:
        boards = GAME_BOARDS
    else:
        boards = DEFAULT_BOARDS

    # 게임사 표본은 일반 테크 표본과 직군 구성이 다르다. 같은 파일에 섞으면
    # 'AI 스택 43.4%' 같은 기존 수치의 모집단이 조용히 바뀐다.
    tag = args.tag or ("game" if args.game else "")
    suffix = f"_{tag}" if tag else ""

    session = requests.Session()
    session.headers["User-Agent"] = "hr-data-analysis-study/1.0 (research)"

    print(f"Greenhouse 채용 보드 수집 — 대상 {len(boards)}개\n")

    raw_payload, records, failed = {}, [], []
    for i, board in enumerate(boards, 1):
        status, jobs = fetch_board(session, board)
        if status != 200:
            failed.append((board, status))
            print(f"  [실패] {board:14} HTTP {status}")
            time.sleep(args.sleep)
            continue

        raw_payload[board] = jobs
        picked = [j for j in jobs if not args.dev_only or is_dev(j)]
        records.extend(to_record(board, j) for j in picked)
        print(f"  {i:2}/{len(boards)} {board:14} {len(jobs):4}건"
              + (f" → 개발 {len(picked)}건" if args.dev_only else ""))
        time.sleep(args.sleep)

    if failed:
        names = ", ".join(f"{b}({s})" for b, s in failed)
        if not args.skip_missing:
            raise SystemExit(
                f"\n[중단] 보드 {len(failed)}개 실패: {names}"
                "\n       일부 회사가 빠진 수집분은 국내 JD 와 비교 기준이 달라지므로"
                "\n       저장하지 않습니다. 보드가 실제로 없어진 것이 확인되면"
                "\n       --skip-missing 으로 명시적으로 제외하세요.\n")
        print(f"\n  [경고] {len(failed)}개 보드 제외됨: {names}")

    if not records:
        raise SystemExit("\n[중단] 수집된 공고가 0건\n")

    raw_path = save_raw("greenhouse", raw_payload)

    rows = []
    for r in records:
        body = r["unstructured"]["content"] or ""
        rows.append({
            **r["structured"],
            "position": r["unstructured"]["position"],
            "본문길이": len(body),
            "AI스택": any(mentions(body, k) for k in AI_STACK),
            "전통스택": any(mentions(body, k) for k in CLASSIC_STACK),
        })
    df = pd.DataFrame(rows)

    jobs_path = os.path.join(DATA_DIR, f"global_greenhouse_jobs{suffix}.json")
    with open(jobs_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    csv_path = os.path.join(DATA_DIR, f"global_greenhouse_jobs{suffix}.csv")
    # 본문은 공고당 수 KB 라 CSV 에 넣으면 파일이 수십 MB 가 된다. 원문은 JSON 에만 둔다.
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    record("greenhouse", f"{BASE}/{{board}}/jobs",
           {"boards": len(raw_payload), "content": "true",
            "dev_only": args.dev_only},
           200, len(records), raw_path,
           [f"data/global_greenhouse_jobs{suffix}.json",
            f"data/global_greenhouse_jobs{suffix}.csv"],
           notes=(f"보드 {len(raw_payload)}개 수집"
                  + (f", {len(failed)}개 제외" if failed else "")
                  + ", 인증키 불필요, 현재 게시 중인 공고만(마감분 미포함)"))

    ai, classic = int(df["AI스택"].sum()), int(df["전통스택"].sum())
    print(f"\n[완료] 보드 {len(raw_payload)}개 / 공고 {len(records):,}건")
    print(f"  AI 스택 언급    {ai:,}건 ({ai / len(df):.1%})")
    print(f"  전통 스택 언급  {classic:,}건 ({classic / len(df):.1%})")
    print(f"  원본: {raw_path}")
    print(f"  가공: data/global_greenhouse_jobs{suffix}.json / .csv")
    print("\n※ 현재 게시 중인 공고만 받습니다. first_published 로 월별 집계를 내면"
          "\n  마감 공고가 빠져 과거가 과소 계상됩니다. 시계열은 HN 수집분을 쓰세요.")


if __name__ == "__main__":
    main()
