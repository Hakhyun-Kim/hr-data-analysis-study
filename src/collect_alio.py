"""공공부문 채용 공고 수집 — 잡알리오(공공기관 채용정보) 오픈API.

국내 JD 수집분의 가장 큰 한계는 **단면**이라는 점이다. 채용 플랫폼에서 과거 공고를
받을 수 없어 "국내에서도 스택이/진입문이 이동했다"는 시계열 주장을 하지 못했다.

잡알리오는 공공기관이 게시한 채용 공고를 공고 시작일과 함께 누적 보관한다.
민간이 아니라 공공부문이라는 한계는 있지만, **국내 채용 데이터 중 시계열이 있는 몇 안 되는
공개 소스**이고 신입/경력 구분이 자유 텍스트가 아니라 코드값으로 들어 있다.

API 사용법 주의 (실측 2026-08-11)
  · `numOfRows` 상한은 1000 이다. 2000 을 넣어도 오류 없이 1000 건만 온다.
  · `pbancBgngYmd` 는 "그 날짜 **이후**" 필터다. 특정일 일치가 아니다.
  · `startDate` / `endDate` 는 **조용히 무시된다.** 오류도 안 나고 totalCount 도 안 줄어든다.
    국민연금 API 의 snake_case 문제와 같은 유형이라 필터가 먹었는지 항상 totalCount 로 확인한다.
  · 개발계정 한도는 일 1,000회다. 전체 수집은 113회면 끝나지만, 조건을 잘못 걸어
    페이지를 반복하면 한도를 태운다. --max-calls 로 상한을 먼저 막는다.

신입 판정
  recrutSe 는 R2010(신입) / R2020(경력) / R2030(신입+경력) 세 값이다.
  "신입이 지원할 수 있는 공고" 는 **R2010 + R2030** 이다. R2010 만 세면 신입 통합 공고가
  빠져 과소 계상된다.

실행 예시:
  python src/collect_alio.py --start 20200101
  python src/collect_alio.py --start 20260101 --ongoing
"""

import argparse
import json
import os
import sys
import time
from urllib.parse import unquote

import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from provenance import DATA_DIR, record, require_env, save_raw  # noqa: E402

ENDPOINT = "https://apis.data.go.kr/1051000/recruitment/list"
TIMEOUT = 40
MAX_ROWS = 1000  # 실측 상한. 이보다 크게 요청해도 1000건만 온다.

RECRUT_SE = {"R2010": "신입", "R2020": "경력", "R2030": "신입+경력"}
ENTRY_OPEN = ("R2010", "R2030")  # 신입이 지원 가능한 구분

# 코드값은 문서가 아니라 2026-08-11 수집분 86,635건에서 코드-이름 쌍을 직접 뽑아 확인했다.
NCS_IT = "R600020"        # 정보통신 (전체 25개 대분류 중, 2020년 이후 6,971건)
HIRE_REGULAR = "R1010"    # 정규직 (비정규직 R1040 / 무기계약직 R1030 / 청년인턴 R1060·R1070)

# 본문 성격의 긴 필드. 원본(JSON)에는 남기고 CSV 에서는 뺀다.
# 공고당 수 KB 라 CSV 에 넣으면 파일이 수십 MB 가 되고 표 계산에도 쓰이지 않는다.
LONG_FIELDS = ("aplyQlfcCn", "disqlfcRsn", "scrnprcdrMthdExpln", "prefCn",
               "prefCondCn", "files", "steps")


def fetch_page(session: requests.Session, key: str, page: int,
               rows: int, params: dict) -> dict:
    resp = session.get(ENDPOINT, params={
        "serviceKey": key, "resultType": "json",
        "pageNo": page, "numOfRows": rows, **params,
    }, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise SystemExit(f"\n[중단] 잡알리오 응답 HTTP {resp.status_code}"
                         f"\n       {resp.text[:200]}\n")
    try:
        return resp.json()
    except ValueError:
        raise SystemExit(f"\n[중단] JSON 파싱 실패\n       {resp.text[:200]}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="잡알리오 공공기관 채용정보 수집")
    parser.add_argument("--start", default="20200101",
                        help="공고 시작일 하한 YYYYMMDD (기본 20200101 — HN 수집 구간과 정렬)")
    parser.add_argument("--ongoing", action="store_true", help="진행 중인 공고만")
    parser.add_argument("--it-only", action="store_true",
                        help=f"NCS 정보통신({NCS_IT}) 직무만 — 민간 개발 JD 와 비교할 때")
    parser.add_argument("--regular-only", action="store_true",
                        help=f"정규직({HIRE_REGULAR})만 — 인턴·비정규직 제외")
    parser.add_argument("--ncs", default="", help="NCS 직무 대분류 코드 직접 지정")
    parser.add_argument("--hire-type", default="", help="고용형태 코드 직접 지정")
    parser.add_argument("--rows", type=int, default=MAX_ROWS, help=f"페이지당 건수 (상한 {MAX_ROWS})")
    parser.add_argument("--max-calls", type=int, default=900,
                        help="호출 수 상한. 개발계정 일 한도 1,000회를 넘기지 않기 위한 안전장치")
    parser.add_argument("--sleep", type=float, default=0.2, help="요청 간 대기(초)")
    args = parser.parse_args()

    key = require_env(
        "DATA_GO_KR_SERVICE_KEY",
        "https://www.data.go.kr → '공공기관 채용정보 조회서비스' 검색 → 활용신청(자동승인)")
    # 포털이 주는 Encoding 키를 그대로 보내면 requests 가 % 를 한 번 더 인코딩해
    # 이중 인코딩으로 인증에 실패한다. collect_nps_companies 와 같은 처리를 한다.
    key = unquote(key) if "%" in key else key
    rows = min(args.rows, MAX_ROWS)

    filters = {"pbancBgngYmd": args.start}
    if args.ongoing:
        filters["ongoingYn"] = "Y"
    ncs = args.ncs or (NCS_IT if args.it_only else "")
    hire = args.hire_type or (HIRE_REGULAR if args.regular_only else "")
    if ncs:
        filters["ncsCdLst"] = ncs
    if hire:
        filters["hireTypeLst"] = hire

    # 필터를 걸면 출력 파일명에 코드를 붙인다. 전체 수집분을 덮어쓰면
    # 어떤 모집단으로 만든 표인지 파일만 보고 알 수 없게 된다.
    suffix = "".join("_" + c for c in (ncs, hire) if c)

    session = requests.Session()
    session.headers["User-Agent"] = "hr-data-analysis-study/1.0 (research)"

    print(f"잡알리오 수집 시작 — 공고 시작일 {args.start} 이후"
          + (" / 진행 중만" if args.ongoing else "")
          + (f" / 필터 {ncs or ''} {hire or ''}".rstrip() if suffix else "") + "\n")

    first = fetch_page(session, key, 1, rows, filters)
    total = int(first.get("totalCount") or 0)
    if not total:
        raise SystemExit("\n[중단] 조건에 맞는 공고 0건 — 필터를 확인하세요\n")

    pages = -(-total // rows)
    print(f"  대상 {total:,}건 / {rows}건씩 {pages}페이지")
    if pages > args.max_calls:
        raise SystemExit(
            f"\n[중단] 필요한 호출 {pages}회 > 상한 {args.max_calls}회"
            f"\n       개발계정 일 한도(1,000회)를 태우게 됩니다."
            f"\n       --start 로 기간을 좁히거나 --max-calls 를 명시적으로 올리세요.\n")

    records, seen, calls = [], set(), 1
    for page in range(1, pages + 1):
        payload = first if page == 1 else fetch_page(session, key, page, rows, filters)
        if page > 1:
            calls += 1
        items = payload.get("result") or []
        if not items:
            print(f"  [경고] {page}페이지 0건 — 조기 종료")
            break

        for item in items:
            sn = item.get("recrutPblntSn")
            if sn in seen:  # 수집 도중 새 공고가 올라오면 페이지가 밀려 중복이 생긴다
                continue
            seen.add(sn)
            records.append(item)

        if page % 20 == 0 or page == pages:
            print(f"  {page}/{pages}페이지 (누적 {len(records):,}건)")
        time.sleep(args.sleep)

    if not records:
        raise SystemExit("\n[중단] 수집된 공고가 0건\n")

    raw_path = save_raw("alio_recruitment", records)

    df = pd.DataFrame([{k: v for k, v in r.items() if k not in LONG_FIELDS}
                       for r in records])
    df["공고시작월"] = df["pbancBgngYmd"].astype(str).str[:6]
    df["구분"] = df["recrutSe"].map(RECRUT_SE)
    df["신입가능"] = df["recrutSe"].isin(ENTRY_OPEN)
    df["채용인원"] = pd.to_numeric(df["recrutNope"], errors="coerce")

    out = os.path.join(DATA_DIR, f"alio_recruitment{suffix}.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")

    monthly = (df.groupby("공고시작월")
                 .agg(공고수=("recrutPblntSn", "count"),
                      채용인원=("채용인원", "sum"),
                      신입가능공고=("신입가능", "sum"))
                 .reset_index())
    monthly["신입가능비중"] = (monthly["신입가능공고"] / monthly["공고수"]).round(4)
    monthly_out = os.path.join(DATA_DIR, f"alio_monthly{suffix}.csv")
    monthly.to_csv(monthly_out, index=False, encoding="utf-8-sig")

    record("alio_recruitment", ENDPOINT,
           {"serviceKey": "<masked>", "numOfRows": rows, "pages": pages, **filters},
           200, len(records), raw_path,
           [f"data/alio_recruitment{suffix}.csv", f"data/alio_monthly{suffix}.csv"],
           notes=(f"{args.start} 이후 공고, API 신고 총건수 {total:,} / 수집 {len(records):,}, "
                  f"호출 {calls}회"))

    entry = int(df["신입가능"].sum())
    print(f"\n[완료] 공고 {len(records):,}건 / 호출 {calls}회")
    print(f"  기간: {df['공고시작월'].min()} ~ {df['공고시작월'].max()}")
    print(f"  신입 지원 가능 {entry:,}건 ({entry / len(df):.1%}) "
          f"— 신입 {int((df['recrutSe'] == 'R2010').sum()):,} + "
          f"신입·경력 {int((df['recrutSe'] == 'R2030').sum()):,}")
    print(f"  채용인원 합계 {int(df['채용인원'].sum()):,}명 "
          f"(인원 미기재 {int(df['채용인원'].isna().sum()):,}건)")
    print(f"  원본: {raw_path}")
    print(f"  가공: data/alio_recruitment{suffix}.csv / alio_monthly{suffix}.csv")

    if ncs:
        # recrutNope 는 공고 단위 인원이다. 한 공고가 여러 NCS 직무를 묶어 뽑으면
        # 직무로 걸러도 그 공고의 전체 인원이 따라온다(수집분 86,635건 중 26,997건이 복수 직무).
        print(f"\n※ 직무 필터를 걸었으므로 '채용인원'은 상한값입니다. 한 공고가 여러 직무를"
              f"\n  묶어 뽑는 경우 해당 공고 인원 전체가 포함됩니다. 비교에는 공고 수를 쓰세요.")
    print("\n※ 공공기관 공고입니다. 민간 JD 의 신입 비중과 직접 비교하면 안 됩니다."
          "\n  공공은 통합 공개채용 비중이 커서 신입 가능 공고가 구조적으로 많습니다."
          "\n  비교하려면 --it-only --regular-only 로 맞춘 뒤 compare_entry_level.py 를 쓰세요.")


if __name__ == "__main__":
    main()
