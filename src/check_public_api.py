"""국가/공공 정형 데이터 실수집 스크립트.

이 스크립트는 인증키가 없거나 API가 실패하면 **즉시 중단**한다.
샘플/예시 수치를 대신 채워 넣지 않는다. (이전 버전의 하드코딩 문제 제거)

필요 환경변수
  KOSIS_API_KEY          https://kosis.kr/openapi  → 회원가입 후 즉시 발급(무료)
  DATA_GO_KR_SERVICE_KEY https://www.data.go.kr    → 국민연금공단_국민연금 가입 사업장 내역 활용신청
  WORKNET_API_KEY        https://openapi.work.go.kr → 고용24/워크넷 오픈API 인증키 신청

실행 예시(PowerShell):
  $env:KOSIS_API_KEY = '...'
  python src/check_public_api.py --source kosis
"""

import argparse
import json
import os
import re
import sys
from urllib.parse import unquote

import pandas as pd
import requests

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")  # SystemExit 메시지도 한글 출력되어야 함

from provenance import DATA_DIR, ROOT, record, require_env, save_raw  # noqa: E402

TIMEOUT = 30


def _fail(source: str, message: str) -> None:
    raise SystemExit(f"\n[중단] {source} 수집 실패: {message}\n")


def _out(name: str) -> str:
    return os.path.join(DATA_DIR, name)


def _rel(path: str) -> str:
    return os.path.relpath(path, ROOT).replace("\\", "/")


# ---------------------------------------------------------------- KOSIS
def collect_kosis(table_id: str, org_id: str, itm_id: str, obj_l1: str,
                  start: str, end: str) -> None:
    """KOSIS 통계표 조회.

    기본값은 '산업별 계절조정 취업자'(DT_1DA9003S) 월별 시계열.
    이 표에서 objL1=58 이 'J 정보통신업'이며, 본 프로젝트의 핵심 정형 지표다.
    (초기 버전이 쓰던 DT_1DA7001S는 '성별 경제활동인구 총괄'로, 산업 구분이 없어 부적합)
    """
    api_key = require_env(
        "KOSIS_API_KEY",
        "https://kosis.kr/openapi 회원가입 → 활용신청 → 즉시 발급(무료)",
    )
    endpoint = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
    params = {
        "method": "getList",
        "apiKey": api_key,
        "itmId": itm_id,
        "objL1": obj_l1,
        "format": "json",
        "jsonVD": "Y",
        "prdSe": "M",
        "startPrdDe": start,
        "endPrdDe": end,
        "orgId": org_id,
        "tblId": table_id,
    }

    resp = requests.get(endpoint, params=params, timeout=TIMEOUT)
    if resp.status_code != 200:
        _fail("KOSIS", f"HTTP {resp.status_code}")

    payload = resp.json()
    # KOSIS는 오류도 HTTP 200 + {"err": "..."} 형태로 반환한다.
    if isinstance(payload, dict) and "err" in payload:
        _fail("KOSIS", f"{payload.get('err')} / {payload.get('errMsg')}")
    if not isinstance(payload, list) or not payload:
        _fail("KOSIS", "응답이 비어 있음 (통계표 ID/기간 파라미터 확인 필요)")

    raw_path = save_raw("kosis", payload)
    df = pd.DataFrame(
        [
            {
                "통계표명": row.get("TBL_NM"),
                "시점": row.get("PRD_DE"),
                "분류": row.get("C1_NM"),
                "항목명": row.get("ITM_NM"),
                "단위": row.get("UNIT_NM"),
                "수치값": row.get("DT"),
            }
            for row in payload
        ]
    )
    out = _out("kosis_employment.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")

    record("kosis", endpoint, params, resp.status_code, len(df), raw_path, [_rel(out)],
           notes=f"tblId={table_id}, itmId={itm_id}, objL1={obj_l1}, {start}~{end}")
    print(f"[OK] KOSIS {len(df)}행 수집 → {_rel(out)} (원본: {raw_path})")


# ------------------------------------------------------- 국민연금 (data.go.kr)
def collect_nps(rows: int, pages: int, sido_code: str = "") -> None:
    """국민연금 가입 사업장 내역. 사업장별 가입자수/신규취득/상실 인원 제공."""
    service_key = require_env(
        "DATA_GO_KR_SERVICE_KEY",
        "https://www.data.go.kr → '국민연금공단_국민연금 가입 사업장 내역' 활용신청 → 일반 인증키(Decoding)",
    )
    # 포털이 Encoding/Decoding 두 벌을 준다. Encoding 키를 그대로 쓰면 requests 가
    # 한 번 더 인코딩해 SERVICE_KEY_IS_NOT_REGISTERED_ERROR 가 난다. 항상 디코딩해서 보낸다.
    if "%" in service_key:
        service_key = unquote(service_key)

    endpoint = "http://apis.data.go.kr/B552015/NpsBplcInfoInqireServiceV2/getBassInfoSearchV2"

    collected, status, total_count = [], None, None
    for page in range(1, pages + 1):
        params = {
            "serviceKey": service_key,
            "pageNo": page,
            "numOfRows": rows,
            "dataType": "JSON",
        }
        if sido_code:
            params["ldong_addr_mgpl_dg_cd"] = sido_code

        resp = requests.get(endpoint, params=params, timeout=TIMEOUT)
        status = resp.status_code
        if status != 200:
            _fail("국민연금", f"HTTP {status} / {resp.text[:200]}")

        try:
            payload = resp.json()
        except json.JSONDecodeError:
            _fail("국민연금", f"JSON 파싱 실패 (인증키 오류 가능): {resp.text[:200]}")

        if "OpenAPI_ServiceResponse" in payload:
            header = payload["OpenAPI_ServiceResponse"].get("cmmMsgHeader", {})
            _fail("국민연금", f"{header.get('errMsg')} / {header.get('returnAuthMsg')}")

        body = payload.get("response", {}).get("body", {}) or {}
        total_count = body.get("totalCount", total_count)
        items = (body.get("items") or {}).get("item", [])
        if isinstance(items, dict):
            items = [items]
        if not items:
            break
        collected.extend(items)

    if not collected:
        _fail(
            "국민연금",
            f"인증은 통과했으나(resultCode 00) 조회 결과가 0건입니다 (totalCount={total_count}).\n"
            "       원인 후보: ① data.go.kr 활용신청 승인 반영 대기(보통 수십 분~1일)\n"
            "                  ② 개발계정 트래픽 미할당\n"
            "       → 포털 '마이페이지 > 오픈API > 개발계정'에서 승인 상태를 확인한 뒤 재시도하세요.",
        )

    raw_path = save_raw("nps", collected)
    df = pd.DataFrame(collected)
    out = _out("national_pension.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")

    record("nps", endpoint,
           {"serviceKey": "<masked>", "numOfRows": rows, "pages": pages,
            "ldong_addr_mgpl_dg_cd": sido_code or "(전체)"},
           status, len(df), raw_path, [_rel(out)], notes=f"totalCount={total_count}")
    print(f"[OK] 국민연금 {len(df)}행 수집 → {_rel(out)} (원본: {raw_path})")


# ---------------------------------------------------------------- 워크넷
def collect_worknet(display: int, pages: int, occupation: str = "", career: str = "") -> None:
    """워크넷(고용24) 채용정보 목록.

    엔드포인트가 openapi.work.go.kr → work24.go.kr 로 이관됐다.
    display 최대 100, startPage 최대 1000. returnType 은 XML 고정.
    """
    auth_key = require_env(
        "WORKNET_API_KEY",
        "https://www.work24.go.kr → 오픈API 활용신청 (기업/사업자 회원 필요)",
    )
    endpoint = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do"

    frames, status, total = [], None, None
    for page in range(1, pages + 1):
        params = {
            "authKey": auth_key,
            "callTp": "L",
            "returnType": "XML",
            "startPage": page,
            "display": min(display, 100),  # 사양상 최대 100
        }
        if occupation:
            params["occupation"] = occupation
        if career:
            params["career"] = career

        resp = requests.get(endpoint, params=params, timeout=TIMEOUT)
        status = resp.status_code
        if status != 200:
            _fail("워크넷", f"HTTP {status}")

        text = resp.text
        if "개인회원은 사용할 수 없는" in text:
            _fail(
                "워크넷",
                "개인회원 계정으로는 사용할 수 없는 API입니다.\n"
                "       → work24.go.kr 에서 기업회원(사업자) 전환 후 재신청이 필요합니다.",
            )
        if "인증키" in text and "<error>" in text:
            _fail("워크넷", f"인증 오류: {text[:200]}")

        if total is None:
            match = re.search(r"<total>(\d+)</total>", text)
            total = match.group(1) if match else None

        try:
            page_frame = pd.read_xml(text, xpath=".//wanted")
        except ValueError:
            _fail("워크넷", f"XML 파싱 실패 / 응답 앞부분: {text[:300]}")
        if page_frame.empty:
            break
        frames.append(page_frame)

    if not frames:
        _fail("워크넷", f"수집된 공고가 0건 (total={total})")

    df = pd.concat(frames, ignore_index=True)
    raw_path = save_raw("worknet", df.to_dict(orient="records"))
    out = _out("worknet_jobs.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")

    record("worknet", endpoint,
           {"authKey": "<masked>", "display": display, "pages": pages,
            "occupation": occupation or "(전체)", "career": career or "(전체)"},
           status, len(df), raw_path, [_rel(out)], notes=f"total={total}")
    print(f"[OK] 워크넷 {len(df)}행 수집 → {_rel(out)} (원본: {raw_path})")


def main() -> None:
    parser = argparse.ArgumentParser(description="국가/공공 정형 데이터 실수집")
    parser.add_argument("--source", choices=["kosis", "nps", "worknet", "all"], default="all")
    parser.add_argument("--kosis-table", default="DT_1DA9003S",
                        help="KOSIS 통계표 ID (기본: 산업별 계절조정 취업자)")
    parser.add_argument("--kosis-org", default="101", help="KOSIS 기관 ID (101=통계청)")
    parser.add_argument("--kosis-itm", default="T30", help="항목 ID (T30=취업자)")
    parser.add_argument("--kosis-obj", default="ALL",
                        help="분류 ID (ALL=전산업, 58=J 정보통신업)")
    parser.add_argument("--start", default="202001", help="조회 시작 YYYYMM")
    parser.add_argument("--end", default="202606", help="조회 종료 YYYYMM")
    parser.add_argument("--rows", type=int, default=100)
    parser.add_argument("--pages", type=int, default=3)
    parser.add_argument("--nps-sido", default="", help="국민연금 시도코드 (11=서울)")
    parser.add_argument("--occupation", default="", help="워크넷 직종코드 (예: 133|134)")
    parser.add_argument("--career", default="",
                        help="워크넷 경력코드 (N=신입, E=경력, Z=무관)")
    args = parser.parse_args()

    print("국가/공공 정형 데이터 실수집 시작 (인증키 없으면 중단, 대체값 생성 없음)\n")

    if args.source in ("kosis", "all"):
        collect_kosis(args.kosis_table, args.kosis_org, args.kosis_itm,
                      args.kosis_obj, args.start, args.end)
    if args.source in ("nps", "all"):
        collect_nps(args.rows, args.pages, args.nps_sido)
    if args.source in ("worknet", "all"):
        collect_worknet(args.rows, args.pages, args.occupation, args.career)


if __name__ == "__main__":
    main()
