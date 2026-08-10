"""국내 채용 플랫폼 JD에 등장한 기업의 국민연금 고용 데이터 수집.

정형(국민연금 가입자수·입퇴사) × 비정형(JD 텍스트)을 **기업 단위로** 결합하기 위한 수집기.

API 사용법 주의 (docs/data_source_access.md 참조)
  · 요청 파라미터는 snake_case 가 아니라 **camelCase** 다.
    snake_case 를 쓰면 서버가 조용히 무시하고 totalCount=0 을 돌려준다. (오류가 아니라 빈 결과)
  · 인증키는 Decoding 값을 써야 한다. Encoding 값은 이중 인코딩돼 인증 실패한다.

파이프라인
  1) getBassInfoSearchV2  : 사업장명 검색 → seq 획득
  2) getDetailInfoSearchV2: seq → 업종, 총가입자수
  3) getPdAcctoSttusInfoSearchV2 : seq → 당월 신규취득(입사)/상실(퇴사)

실행 예시:
  python src/collect_nps_companies.py
"""

import argparse
import json
import os
import re
import sys
import time
from urllib.parse import unquote

import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from provenance import DATA_DIR, record, require_env, save_raw  # noqa: E402

BASE = "https://apis.data.go.kr/B552015/NpsBplcInfoInqireServiceV2"
TIMEOUT = 30


def tag(xml: str, name: str) -> str | None:
    match = re.search(rf"<{name}>(.*?)</{name}>", xml, re.S)
    return match.group(1).strip() if match else None


def items(xml: str) -> list[str]:
    return re.findall(r"<item>(.*?)</item>", xml, re.S)


def normalize(name: str) -> str:
    """'(주)토스 (비바리퍼블리카)' → '토스' 처럼 검색용으로 정리한다.

    채용 플랫폼은 브랜드명, 국민연금은 법인등기명을 쓰기 때문에 완전 일치는 기대할 수 없다.
    """
    name = re.sub(r"\([^)]*\)", " ", name)          # 괄호 주석 제거
    name = re.sub(r"주식회사|㈜|\(주\)|\(유\)|유한회사", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def key_of(name: str) -> str:
    """비교용 키. 공백까지 제거해 '주식회사 긴트'와 '주식회사긴트'를 동일 취급한다."""
    return normalize(name).replace(" ", "")


class NpsClient:
    def __init__(self, key: str):
        self.key = unquote(key) if "%" in key else key
        self.session = requests.Session()

    def get(self, op: str, **params) -> str:
        params = {"serviceKey": self.key, **params}
        for attempt in range(3):
            try:
                resp = self.session.get(f"{BASE}/{op}", params=params, timeout=TIMEOUT)
                if resp.status_code == 200:
                    return resp.text
            except requests.RequestException:
                pass
            time.sleep(1.0 * (attempt + 1))
        return ""

    def search(self, name: str) -> list[dict]:
        # camelCase 필수. snake_case 는 무시되어 빈 결과가 돌아온다.
        xml = self.get("getBassInfoSearchV2", wkplNm=name, pageNo=1, numOfRows=50)
        out = []
        for block in items(xml):
            out.append({
                "seq": tag(block, "seq"),
                "wkplNm": tag(block, "wkplNm"),
                "addr": tag(block, "wkplRoadNmDtlAddr"),
                "dataCrtYm": tag(block, "dataCrtYm"),
                "jnngStcd": tag(block, "wkplJnngStcd"),  # 1=등록, 2=탈퇴
            })
        return out

    def detail(self, seq: str) -> dict:
        xml = self.get("getDetailInfoSearchV2", seq=seq)
        block = items(xml)
        if not block:
            return {}
        b = block[0]
        return {
            "업종명": tag(b, "vldtVlKrnNm"),
            "업종코드": tag(b, "wkplIntpCd"),
            "가입자수": tag(b, "jnngpCnt"),
            "당월고지금액": tag(b, "crrmmNtcAmt"),
            "적용일자": tag(b, "adptDt"),
        }

    def period(self, seq: str) -> dict:
        xml = self.get("getPdAcctoSttusInfoSearchV2", seq=seq, pageNo=1, numOfRows=100)
        block = items(xml)
        if not block:
            return {}
        b = block[0]
        return {"신규취득자수": tag(b, "nwAcqzrCnt"), "상실자수": tag(b, "lssJnngpCnt")}


def pick_match(candidates: list[dict], query: str) -> dict | None:
    """정규화 후 **완전 일치**하는 사업장만 채택한다.

    부분 일치를 허용하면 상호 앞부분만 같은 무관한 업종의 사업장이 붙는다.
    검색 API가 부분 문자열로 매칭하기 때문에, 후보 중 아무거나 고르는 폴백을 두면 안 된다.
    매칭을 놓치는 편이 틀린 기업을 붙이는 것보다 낫다.
    """
    target = key_of(query)
    exact = [c for c in candidates if key_of(c.get("wkplNm") or "") == target]
    if not exact:
        return None
    # 동명 사업장이 여럿이면 활성(등록) 상태를 우선한다.
    active = [c for c in exact if c.get("jnngStcd") == "1"]
    return (active or exact)[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="공고 게재 기업의 국민연금 고용 데이터 수집")
    parser.add_argument("--limit", type=int, default=0, help="처리할 기업 수 제한 (0=전체)")
    args = parser.parse_args()

    key = require_env(
        "DATA_GO_KR_SERVICE_KEY",
        "https://www.data.go.kr → '국민연금공단_국민연금 가입 사업장 내역' 활용신청",
    )

    jobs_path = os.path.join(DATA_DIR, "domestic_jobs.json")
    if not os.path.exists(jobs_path):
        raise SystemExit("\n[중단] data/domestic_jobs.json 없음 → collect_jobs.py 먼저 실행\n")

    with open(jobs_path, "r", encoding="utf-8") as f:
        jobs = json.load(f)

    companies = sorted({
        j["structured"]["company_name"]
        for j in jobs if j["structured"].get("company_name")
    })
    if args.limit:
        companies = companies[: args.limit]

    print(f"공고 게재 기업 {len(companies)}개에 국민연금 데이터 매칭 시작\n")

    client = NpsClient(key)
    rows, unmatched = [], []

    for i, original in enumerate(companies, 1):
        query = normalize(original)
        if not query:
            unmatched.append(original)
            continue

        candidates = client.search(query)
        best = pick_match(candidates, query)
        if not best or not best.get("seq"):
            unmatched.append(original)
        else:
            row = {
                "플랫폼_회사명": original,
                "검색어": query,
                "국민연금_사업장명": best["wkplNm"],
                "seq": best["seq"],
                "주소": best["addr"],
                "기준년월": best["dataCrtYm"],
                "후보수": len(candidates),
            }
            row.update(client.detail(best["seq"]))
            row.update(client.period(best["seq"]))
            rows.append(row)

        if i % 25 == 0:
            print(f"  {i}/{len(companies)} 처리 (매칭 {len(rows)}, 미매칭 {len(unmatched)})")
        time.sleep(0.1)

    if not rows:
        raise SystemExit("\n[중단] 매칭된 기업이 0건\n")

    raw_path = save_raw("nps_companies", {"matched": rows, "unmatched": unmatched})

    df = pd.DataFrame(rows)
    for col in ["가입자수", "신규취득자수", "상실자수"]:
        df[col] = pd.to_numeric(df.get(col), errors="coerce")
    # 입사율/퇴사율은 분모(가입자수)가 있을 때만 계산한다.
    df["입사율(%)"] = (df["신규취득자수"] / df["가입자수"] * 100).round(2)
    df["퇴사율(%)"] = (df["상실자수"] / df["가입자수"] * 100).round(2)
    df["순증감"] = df["신규취득자수"] - df["상실자수"]

    out = os.path.join(DATA_DIR, "nps_companies.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")

    rate = len(rows) / len(companies)
    record("nps_companies", f"{BASE}/getBassInfoSearchV2",
           {"serviceKey": "<masked>", "기업수": len(companies), "매칭방식": "wkplNm 검색"},
           200, len(df), raw_path, ["data/nps_companies.csv"],
           notes=f"매칭률 {rate:.1%} ({len(rows)}/{len(companies)}), 미매칭 {len(unmatched)}건")

    print(f"\n[완료] 매칭 {len(rows)}/{len(companies)}개 ({rate:.1%})")
    print(f"  원본: {raw_path}")
    print(f"  가공: data/nps_companies.csv")
    print(f"  ※ 미매칭 {len(unmatched)}건은 국내 채용 플랫폼 브랜드명과 법인등기명이 달라 발생 "
          f"(예: {unmatched[:3]})")


if __name__ == "__main__":
    main()
