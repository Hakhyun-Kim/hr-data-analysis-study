"""수집된 JD의 공용 로딩·정제 모듈.

분석 스크립트와 시각화 스크립트가 **같은 모집단**을 보도록 정제 규칙을 한 곳에 둔다.
규칙이 흩어지면 보고서 수치와 그래프 수치가 어긋난다.

정제 대상 (2026-08-10 검증에서 발견)
  1. 중복 게시: 한 회사가 동일 본문 JD를 최대 5건까지 올린다.
  2. 비개발 직군: xAI 'AI Tutor - {언어}' 14건은 언어 데이터 라벨링이지 개발 공고가 아니다.
"""

import json
import os
import re

from provenance import DATA_DIR

# 비개발 직군 패턴. 오탐을 피하기 위해 확실한 것만 좁게 잡는다.
# ('운영', 'PM' 등은 정상적인 테크 직군에도 흔히 쓰여 제외 대상으로 삼지 않는다)
NON_DEV_PATTERNS = [
    r"\bAI\s*Tutor\b",
    r"튜터",
    r"\bTranscriber\b",
    r"\bAnnotator\b",
]

SIGNATURE_LEN = 200  # 중복 판정에 쓸 본문 앞부분 길이

# 국민연금 업종명 중 소프트웨어·IT로 볼 패턴.
# 분석과 그래프가 같은 모집단을 쓰도록 여기 한 곳에서만 정의한다.
SW_INDUSTRY = "소프트웨어|데이터베이스|정보 제공|시스템 통합|컴퓨터 프로그래밍"


def body_text(job: dict) -> str:
    """스택 분석 대상 본문: 자격요건 + 우대사항."""
    u = job["unstructured"]
    return " ".join(filter(None, [u.get("requirements"), u.get("preferred_points")]))


def is_non_dev(job: dict) -> bool:
    position = job["unstructured"].get("position") or ""
    return any(re.search(p, position, re.IGNORECASE) for p in NON_DEV_PATTERNS)


def load_jobs(clean: bool = True, verbose: bool = True) -> tuple[list, dict]:
    """수집 JD를 로드한다. clean=True면 중복·비개발 공고를 제거한다.

    Returns: (jobs, report) — report는 제거 내역이며 보고서에 그대로 기재할 수 있다.
    """
    path = os.path.join(DATA_DIR, "domestic_jobs.json")
    if not os.path.exists(path):
        raise SystemExit("\n[중단] data/domestic_jobs.json 없음 → collect_jobs.py 먼저 실행\n")

    with open(path, "r", encoding="utf-8") as f:
        jobs = json.load(f)

    report = {"원본": len(jobs), "비개발제거": 0, "중복제거": 0, "최종": len(jobs)}
    if not clean:
        return jobs, report

    kept, seen = [], set()
    for job in jobs:
        if is_non_dev(job):
            report["비개발제거"] += 1
            continue
        # 같은 회사가 올린 동일 본문은 1건으로 축약한다.
        signature = (
            job["structured"].get("company_name"),
            (job["unstructured"].get("requirements") or "")[:SIGNATURE_LEN],
        )
        if signature in seen:
            report["중복제거"] += 1
            continue
        seen.add(signature)
        kept.append(job)

    report["최종"] = len(kept)

    if verbose:
        print(f"[정제] 원본 {report['원본']}건 → 비개발 -{report['비개발제거']}건, "
              f"중복 -{report['중복제거']}건 → 분석 대상 {report['최종']}건")

    return kept, report
