"""EIS 고용행정통계 구인·구직 현황(OPIA) 수집.

워크넷 채용정보 OPEN-API가 기업회원 전용이라 개인 계정으로 막히는 문제의 우회 경로다.
이 API는 인증키가 필요 없고, 신규구인인원수/신규구직건수를 제공해 구인배율을 직접 계산할 수 있다.

제약 (docs/data_source_access.md 참조)
  · rsdAreaCd(시군구) + sxdsCd(성별) + ageCd(5세연령)이 모두 필수이고 '전체' 코드가 없다.
    → 조합을 전부 순회해야 하므로 호출량이 크다.
  · 직종은 대분류 10개까지만 제공된다. 개발 직군만 분리할 수 없다.

실행 예시:
  python src/collect_eis_vacancy.py --months 12
"""

import argparse
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from provenance import DATA_DIR, ROOT, record, save_raw  # noqa: E402

ENDPOINT = "https://eis.work24.go.kr/opi/joApi.do"
TIMEOUT = 30

# 서울 25개 자치구 (행정표준 시군구코드 5자리)
SEOUL_DISTRICTS = {
    "11110": "종로구", "11140": "중구", "11170": "용산구", "11200": "성동구",
    "11215": "광진구", "11230": "동대문구", "11260": "중랑구", "11290": "성북구",
    "11305": "강북구", "11320": "도봉구", "11350": "노원구", "11380": "은평구",
    "11410": "서대문구", "11440": "마포구", "11470": "양천구", "11500": "강서구",
    "11530": "구로구", "11545": "금천구", "11560": "영등포구", "11590": "동작구",
    "11620": "관악구", "11650": "서초구", "11680": "강남구", "11710": "송파구",
    "11740": "강동구",
}

SEX_CODES = ["M", "F"]           # Z(무관)는 항상 0건이라 제외
AGE_CODES = [f"{i:02d}" for i in range(1, 12)]  # 01~11 (19세이하 ~ 65세이상)

# 응답에서 뽑을 필드
FIELDS = [
    "dwClosYm", "ctpvCdNm", "rsdAreaCd", "rsdAreaCdNm", "sxdsCdNm", "ageCdNm",
    "wnetJsfcLrclCd", "wnetJsfcLrclCdNm", "stdIndLrclCdNm",
    "newJoNmpr", "newJhntNmpr", "empmCt", "valdJoNmpr",
]


def recent_months(end: str, count: int) -> list[str]:
    year, month = int(end[:4]), int(end[4:])
    out = []
    for _ in range(count):
        out.append(f"{year}{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return sorted(out)


def parse_rows(xml_text: str) -> list[dict]:
    """<rqst> 블록을 dict 리스트로 변환. 응답 인코딩은 EUC-KR."""
    rows = []
    for block in re.findall(r"<rqst>(.*?)</rqst>", xml_text, re.S):
        row = {}
        for field in FIELDS:
            match = re.search(rf"<{field}>(.*?)</{field}>", block, re.S)
            row[field] = match.group(1).strip() if match else None
        rows.append(row)
    return rows


class QuotaExceeded(RuntimeError):
    """IP 단위 조회 한도 초과. 계속 호출해도 의미가 없으므로 즉시 중단시킨다."""


def fetch(session: requests.Session, ym: str, area: str, sex: str, age: str) -> list[dict]:
    params = {
        "apiSecd": "OPIA",
        "rernSecd": "XML",
        "closStdrYm": ym,
        "rsdAreaCd": area,
        "sxdsCd": sex,
        "ageCd": age,
        "bgnPage": 1,
        "display": 10000,  # 사양상 10 초과 10000 미만
    }
    for attempt in range(3):
        try:
            resp = session.get(ENDPOINT, params=params, timeout=TIMEOUT)
            resp.encoding = "euc-kr"
            if "HITS_EXCEEDED" in resp.text:
                raise QuotaExceeded("IP 단위 OPEN API 조회 횟수 초과")
            if "<error>" in resp.text:
                message = re.search(r"<error>(.*?)</error>", resp.text, re.S)
                raise RuntimeError(message.group(1).strip() if message else "unknown")
            return parse_rows(resp.text)
        except QuotaExceeded:
            raise
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="EIS 구인·구직 현황 수집")
    parser.add_argument("--months", type=int, default=12, help="수집할 개월 수")
    parser.add_argument("--end", default="", help="종료 기준월 YYYYMM (기본: 2개월 전)")
    parser.add_argument("--workers", type=int, default=6, help="동시 요청 수")
    args = parser.parse_args()

    if args.end:
        end = args.end
    else:
        today = date.today()
        year, month = today.year, today.month - 1
        if month <= 0:
            year, month = year - 1, month + 12
        end = f"{year}{month:02d}"

    months = recent_months(end, args.months)
    combos = [
        (ym, area, sex, age)
        for ym in months
        for area in SEOUL_DISTRICTS
        for sex in SEX_CODES
        for age in AGE_CODES
    ]

    print(f"EIS 구인·구직 수집: 서울 {len(SEOUL_DISTRICTS)}개구 × "
          f"{len(SEX_CODES)}성별 × {len(AGE_CODES)}연령 × {len(months)}개월")
    print(f"기간 {months[0]}~{months[-1]} / 총 {len(combos):,}회 호출 "
          f"(동시 {args.workers})\n")

    rows, failed = [], []
    session = requests.Session()
    done = 0

    quota_hit = False
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch, session, *c): c for c in combos}
        for future in as_completed(futures):
            combo = futures[future]
            done += 1
            try:
                rows.extend(future.result())
            except QuotaExceeded:
                quota_hit = True
                for pending in futures:
                    pending.cancel()
                break
            except Exception as exc:
                failed.append((combo, str(exc)[:60]))
            if done % 500 == 0:
                print(f"  {done:,}/{len(combos):,} 완료 (누적 {len(rows):,}행, 실패 {len(failed)})")

    if quota_hit:
        # 부분 수집분은 지역/연령 커버리지가 들쭉날쭉해 통계로 쓸 수 없다.
        # 편향된 데이터를 파일로 남기지 않는 것이 이 분기의 목적이다.
        raise SystemExit(
            f"\n[중단] IP 단위 조회 한도 초과 (HITS_EXCEEDED). {done:,}/{len(combos):,}회 시점.\n"
            "       EIS OPEN API는 IP당 일일 조회 한도가 있어 대량 순회 수집이 불가능합니다.\n"
            "       부분 수집분은 지역·연령 커버리지가 불균등해 통계로 쓸 수 없으므로 저장하지 않습니다.\n"
            "       → 범위를 줄여(--months 1) 여러 날에 나눠 받거나, 다른 소스를 사용하세요.\n"
        )

    if not rows:
        raise SystemExit("\n[중단] 수집 결과 0행\n")

    raw_path = save_raw("eis_vacancy", rows)

    df = pd.DataFrame(rows)
    for col in ["newJoNmpr", "newJhntNmpr", "empmCt", "valdJoNmpr"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    out = f"{DATA_DIR}/eis_vacancy.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")

    record(
        "eis_opia", ENDPOINT,
        {"apiSecd": "OPIA", "지역": f"서울 {len(SEOUL_DISTRICTS)}개구",
         "기간": f"{months[0]}~{months[-1]}", "호출수": len(combos)},
        200, len(df), raw_path, ["data/eis_vacancy.csv"],
        notes=f"실패 {len(failed)}건 / 인증키 불필요 API",
    )

    print(f"\n[완료] {len(df):,}행 수집 (호출 실패 {len(failed)}건)")
    if failed:
        print(f"  실패 예시: {failed[:3]}")
    print(f"  원본: {raw_path}")
    print(f"  가공: data/eis_vacancy.csv")


if __name__ == "__main__":
    main()
