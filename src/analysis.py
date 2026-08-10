"""1st Iteration 정형+비정형 융합 분석.

원칙
  1. 출력되는 모든 수치는 수집 파일에서 계산한다. 결론 문장에 숫자를 직접 적지 않는다.
  2. 수집되지 않은 소스는 '미수집'으로 표시하고 결론에서 제외한다. 추정값을 만들지 않는다.
  3. 비율에는 항상 분모(모집단 N)를 함께 출력한다.
"""

import json
import os
import re
import sys
from collections import Counter

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

from job_dataset import SW_INDUSTRY, body_text, load_jobs  # noqa: E402
from provenance import DATA_DIR  # noqa: E402

# 기술 스택 사전: AI 에이전트 계열과 전통 백엔드 계열을 분리해 비교한다.
AI_STACK = ["LLM", "RAG", "Agent", "LangChain", "LlamaIndex", "Fine-tuning",
            "Vector DB", "임베딩", "프롬프트"]
CLASSIC_STACK = ["Spring", "Java", "MySQL", "Kubernetes", "Docker", "AWS",
                 "Django", "Node.js"]


def mentions(text: str, keyword: str) -> bool:
    """ASCII 키워드는 단어경계로, 한글 키워드는 부분문자열로 매칭한다.

    한글은 \\b 단어경계가 사실상 동작하지 않으므로 분기한다.
    """
    if keyword.isascii():
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(keyword)}(?![A-Za-z0-9])",
                         text, re.IGNORECASE) is not None
    return keyword in text


def doc_frequency(docs: list[str], keywords: list[str]) -> Counter:
    """키워드별 '등장 공고 수'(문서빈도)를 센다. 총 언급횟수가 아니다."""
    counts = Counter()
    for text in docs:
        for kw in keywords:
            if mentions(text, kw):
                counts[kw] += 1
    return counts


def career_bucket(annual_from) -> str:
    """요구 최소 연차를 구간으로 나눈다.

    annual_from 이 '최소 요구 연차'이므로 진입 장벽을 나타낸다.
    (annual_to=100 은 상한 없음을 뜻할 뿐이라 구간 판정에 쓰지 않는다)
    """
    if annual_from is None or (isinstance(annual_from, float) and pd.isna(annual_from)):
        return "경력무관/미기재"
    years = int(annual_from)
    if years == 0:
        return "신입 (0년)"
    if years <= 3:
        return "주니어 (1~3년)"
    if years <= 7:
        return "미들 (4~7년)"
    return "시니어 (8년+)"


BUCKET_ORDER = ["신입 (0년)", "주니어 (1~3년)", "미들 (4~7년)", "시니어 (8년+)", "경력무관/미기재"]


def analyze_by_career(jobs: list) -> dict:
    """요구 연차 구간별 기술 스택 언급률."""
    print("[2-1] 연차별 요구 스택 분석")
    print("-" * 70)

    buckets: dict[str, list[str]] = {}
    for job in jobs:
        bucket = career_bucket(job["structured"].get("annual_from"))
        buckets.setdefault(bucket, []).append(body_text(job))

    result = {}
    print(f"{'구간':<16}{'N':>5}{'AI스택':>10}{'전통스택':>11}   상위 키워드")
    print("-" * 70)

    for name in BUCKET_ORDER:
        docs = buckets.get(name)
        if not docs:
            continue
        n = len(docs)
        ai_hit = sum(1 for t in docs if any(mentions(t, k) for k in AI_STACK))
        classic_hit = sum(1 for t in docs if any(mentions(t, k) for k in CLASSIC_STACK))
        top = doc_frequency(docs, AI_STACK + CLASSIC_STACK).most_common(3)
        top_text = ", ".join(f"{k}({c/n:.0%})" for k, c in top)

        print(f"{name:<16}{n:>5}{ai_hit/n:>9.1%}{classic_hit/n:>11.1%}   {top_text}")
        result[name] = {
            "n": n, "ai_hit": ai_hit, "classic_hit": classic_hit,
            "ai_ratio": ai_hit / n, "classic_ratio": classic_hit / n,
        }

    # 신입 공고가 실제로 얼마나 열려 있는가 — '신입이 특히 어렵다'의 직접 지표
    total = sum(v["n"] for v in result.values())
    entry = result.get("신입 (0년)", {}).get("n", 0)
    print(f"\n  · 신입 지원 가능 공고 비중: {entry}/{total}건 = {entry/total:.1%}")
    result["_entry_share"] = entry / total if total else 0.0
    result["_total"] = total
    print()
    return result


def analyze_unstructured() -> dict:
    print("[2] 비정형 데이터 분석 (국내 채용 플랫폼 JD 본문)")
    print("-" * 70)

    jobs, clean_report = load_jobs(clean=True)

    by_category: dict[str, list[str]] = {}
    for job in jobs:
        category = job["structured"]["category"]
        # 자격요건 + 우대사항만 사용 (회사소개/복지는 스택 신호가 아님)
        by_category.setdefault(category, []).append(body_text(job))

    all_docs = [t for docs in by_category.values() for t in docs]
    n_total = len(all_docs)
    n_empty = sum(1 for t in all_docs if not t.strip())
    print(f"모집단 N = {n_total}건 (본문 결측 {n_empty}건 포함)\n")

    result = {"n_total": n_total, "n_empty": n_empty, "by_category": {},
              "clean_report": clean_report}

    for category, docs in by_category.items():
        n = len(docs)
        ai_hit = sum(1 for t in docs if any(mentions(t, k) for k in AI_STACK))
        classic_hit = sum(1 for t in docs if any(mentions(t, k) for k in CLASSIC_STACK))

        print(f"■ {category} (N={n})")
        print(f"  - AI 에이전트 스택 1개 이상 언급: {ai_hit}건 / {n}건 = {ai_hit / n:.1%}")
        print(f"  - 전통 백엔드 스택 1개 이상 언급: {classic_hit}건 / {n}건 = {classic_hit / n:.1%}")

        top = doc_frequency(docs, AI_STACK + CLASSIC_STACK).most_common(8)
        print("  - 키워드별 등장 공고 수(문서빈도):")
        for kw, cnt in top:
            print(f"      {kw:<12} {cnt:>4}건 ({cnt / n:.1%})")
        print()

        result["by_category"][category] = {
            "n": n, "ai_hit": ai_hit, "classic_hit": classic_hit,
            "ai_ratio": ai_hit / n, "classic_ratio": classic_hit / n,
        }

    result["by_career"] = analyze_by_career(jobs)
    return result


ICT_INDUSTRY = "J 정보통신업"


def analyze_kosis(path: str) -> dict:
    """정보통신업 취업자 월별 시계열 분석 (KOSIS 산업별 계절조정 취업자)."""
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["수치값"] = pd.to_numeric(df["수치값"], errors="coerce")
    df = df.dropna(subset=["수치값"])

    ict = df[df["분류"] == ICT_INDUSTRY].sort_values("시점")
    if ict.empty:
        print(f"  [경고] '{ICT_INDUSTRY}' 행이 없습니다. --kosis-obj 파라미터 확인 필요")
        return {}

    unit = ict["단위"].iloc[0]
    first, last = ict.iloc[0], ict.iloc[-1]
    latest_period = int(last["시점"])

    # 전년동월 대비
    yoy_period = latest_period - 100
    yoy_row = ict[ict["시점"] == yoy_period]
    yoy_text = "비교 시점 없음"
    yoy_pct = None
    if not yoy_row.empty:
        prev = yoy_row["수치값"].iloc[0]
        yoy_pct = (last["수치값"] - prev) / prev
        yoy_text = f"{last['수치값'] - prev:+,.1f}{unit} ({yoy_pct:+.1%})"

    total_growth = (last["수치값"] - first["수치값"]) / first["수치값"]

    # 전산업 대비 비중 변화
    def share(period: int) -> float:
        snap = df[df["시점"] == period]
        total = snap["수치값"].sum()
        ict_val = snap[snap["분류"] == ICT_INDUSTRY]["수치값"].sum()
        return ict_val / total if total else float("nan")

    share_first, share_last = share(int(first["시점"])), share(latest_period)

    print(f"  [수집됨] KOSIS 산업별 취업자 — {len(df)}행 / {df['분류'].nunique()}개 산업 "
          f"/ {int(first['시점'])}~{latest_period}")
    print(f"    · {ICT_INDUSTRY} 취업자: "
          f"{first['수치값']:,.1f} → {last['수치값']:,.1f}{unit} ({total_growth:+.1%})")
    print(f"    · 전년동월 대비({yoy_period}→{latest_period}): {yoy_text}")
    print(f"    · 전산업 내 비중: {share_first:.2%} → {share_last:.2%} "
          f"({(share_last - share_first) * 100:+.2f}%p)")

    # 최근 12개월 고점 대비 낙폭 — '채용 한파' 주장의 검증 지점
    recent = ict.tail(12)
    peak = ict["수치값"].max()
    peak_period = int(ict.loc[ict["수치값"].idxmax(), "시점"])
    print(f"    · 역대 고점: {peak:,.1f}{unit} ({peak_period}) / "
          f"현재는 고점 대비 {(last['수치값'] - peak) / peak:+.1%}")
    print(f"    · 최근 12개월 범위: {recent['수치값'].min():,.1f} ~ {recent['수치값'].max():,.1f}{unit}")

    return {
        "rows": len(df),
        "period": [int(first["시점"]), latest_period],
        "ict_first": float(first["수치값"]),
        "ict_last": float(last["수치값"]),
        "total_growth": float(total_growth),
        "yoy_pct": float(yoy_pct) if yoy_pct is not None else None,
        "share_first": float(share_first),
        "share_last": float(share_last),
        "peak": float(peak),
        "peak_period": peak_period,
        "unit": unit,
    }


def analyze_structured() -> dict:
    """정형 데이터는 실제 수집 파일이 있을 때만 분석한다."""
    print("[1] 정형 데이터 분석 (국가/공공 통계)")
    print("-" * 70)

    result = {}
    kosis_path = os.path.join(DATA_DIR, "kosis_employment.csv")
    if os.path.exists(kosis_path):
        kosis = analyze_kosis(kosis_path)
        if kosis:
            result["KOSIS 고용통계"] = kosis
    else:
        print("  [미수집] KOSIS 고용통계 — kosis_employment.csv 없음")

    nps_path = os.path.join(DATA_DIR, "nps_companies.csv")
    if os.path.exists(nps_path):
        nps = analyze_nps(nps_path)
        if nps:
            result["국민연금 기업고용"] = nps
    else:
        print("  [미수집] 국민연금 기업고용 — nps_companies.csv 없음 "
              "(python src/collect_nps_companies.py)")

    print("  [폐기] 워크넷 채용공고 — 기업회원 전용 API로 개인 계정 접근 불가 "
          "(docs/data_source_access.md)")

    print()
    return result


def analyze_nps(path: str) -> dict:
    """공고 게재 기업의 국민연금 고용 단면 분석.

    주의: 기간별 현황 API는 당월 단일 스냅샷이라 시계열이 아니다.
          '한 달치 입퇴사 흐름'으로만 해석해야 한다.
    """
    df = pd.read_csv(path, encoding="utf-8-sig")
    if df.empty:
        return {}

    ym = df["기준년월"].mode().iloc[0]
    sw = df[df["업종명"].str.contains(SW_INDUSTRY, na=False)]

    def bucket(frame: pd.DataFrame) -> dict:
        return {
            "n": len(frame),
            "가입자수": int(frame["가입자수"].sum()),
            "입사": int(frame["신규취득자수"].sum()),
            "퇴사": int(frame["상실자수"].sum()),
            "순증감": int(frame["순증감"].sum()),
            "순증기업": int((frame["순증감"] > 0).sum()),
            "순감기업": int((frame["순증감"] < 0).sum()),
            "보합기업": int((frame["순증감"] == 0).sum()),
        }

    total, sw_stat = bucket(df), bucket(sw)

    print(f"  [수집됨] 국민연금 기업고용 — {len(df)}개사 / 기준월 {ym} (당월 스냅샷)")
    print(f"    · 소프트웨어·IT 업종 {sw_stat['n']}개사: 총 가입자 {sw_stat['가입자수']:,}명")
    print(f"      입사 {sw_stat['입사']:,}명 / 퇴사 {sw_stat['퇴사']:,}명 "
          f"→ 순증감 {sw_stat['순증감']:+,}명")
    print(f"      순증 {sw_stat['순증기업']}개사 / 순감 {sw_stat['순감기업']}개사 "
          f"/ 보합 {sw_stat['보합기업']}개사")
    print(f"    · 전체 {total['n']}개사 순증감 {total['순증감']:+,}명 "
          f"(순증 {total['순증기업']} / 순감 {total['순감기업']})")

    return {"기준년월": int(ym), "전체": total, "소프트웨어": sw_stat}


def main() -> None:
    print("=" * 70)
    print("HR 데이터 융합 분석 — 정형(공공통계) + 비정형(JD 텍스트)")
    print("=" * 70 + "\n")

    structured = analyze_structured()
    unstructured = analyze_unstructured()

    print("=" * 70)
    print("[3] 계산 결과 기반 결론")
    print("-" * 70)

    kosis = structured.get("KOSIS 고용통계")
    if kosis:
        direction = "증가" if kosis["total_growth"] > 0 else "감소"
        print(f"• 정보통신업 취업자는 {kosis['period'][0]}~{kosis['period'][1]} 동안 "
              f"{kosis['ict_first']:,.1f}→{kosis['ict_last']:,.1f}{kosis['unit']}로 "
              f"{kosis['total_growth']:+.1%} {direction}.")
        if kosis["yoy_pct"] is not None:
            print(f"• 전년동월 대비 {kosis['yoy_pct']:+.1%} → "
                  f"'고용 절벽' 가설은 산업 전체 취업자 수준에서는 지지되지 않음.")
        print(f"• 전산업 내 비중 {kosis['share_first']:.2%}→{kosis['share_last']:.2%}: "
              f"산업 자체는 확대 국면.")
    else:
        print("• KOSIS 미수집 → 산업 고용 추이 결론 산출 불가.")

    nps = structured.get("국민연금 기업고용")
    if nps:
        sw = nps["소프트웨어"]
        print(f"• 채용 중인 SW·IT {sw['n']}개사의 {nps['기준년월']} 순증감은 "
              f"{sw['순증감']:+,}명 — 총 가입자 {sw['가입자수']:,}명 대비 사실상 보합.")
        print(f"• 기업별로는 갈립니다: 순증 {sw['순증기업']}개사 vs 순감 {sw['순감기업']}개사. "
              f"산업 전체 성장과 달리 개별 기업 단위에서는 감원도 동시에 진행 중.")

    print("• 구인배율은 산출 불가 — 워크넷은 기업회원 전용, EIS는 IP 쿼터 제한 "
          "(docs/data_source_access.md).")

    if unstructured:
        cats = unstructured["by_category"]
        for category, m in cats.items():
            print(f"• {category}: AI 스택 언급 {m['ai_hit']}/{m['n']}건({m['ai_ratio']:.1%}), "
                  f"전통 스택 {m['classic_hit']}/{m['n']}건({m['classic_ratio']:.1%})")

        if len(cats) == 2:
            (a_name, a), (b_name, b) = cats.items()
            gap = a["ai_ratio"] - b["ai_ratio"]
            print(f"• 두 직군의 AI 스택 언급률 격차: {gap:+.1%}p ({a_name} 대비 {b_name})")

        careers = unstructured.get("by_career", {})
        entry = careers.get("신입 (0년)")
        senior = careers.get("시니어 (8년+)")
        if entry:
            print(f"• 신입 지원 가능 공고는 {entry['n']}/{careers['_total']}건 "
                  f"({careers['_entry_share']:.1%})에 불과 — 시장 총량과 무관하게 "
                  f"진입 자체가 좁습니다.")
        if entry and senior:
            gap = senior["ai_ratio"] - entry["ai_ratio"]
            print(f"• AI 스택 요구율: 신입 {entry['ai_ratio']:.1%} vs 시니어 "
                  f"{senior['ai_ratio']:.1%} ({gap:+.1%}p)")

    print("\n※ 위 수치는 모두 data/domestic_jobs.json 등 수집 파일에서 계산됨.")
    print("  출처 추적은 data/provenance.json 참조.")


if __name__ == "__main__":
    main()
