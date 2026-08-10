"""HN 채용글의 요구 연차/레벨 파싱 — 국내 '신입 공고 12.9%'와 비교하기 위한 분석.

측정 방식이 국내와 다르다는 점이 이 분석의 핵심 제약이다.
  · 국내 JD: `annual_from` 이라는 **구조화 필드**. 모든 공고가 값을 가진다.
  · HN 채용글: **자유 텍스트**. 대부분 레벨을 아예 언급하지 않는다.

그래서 전체 대비 비율을 그대로 비교하면 HN 쪽이 과소 추정된다.
**레벨을 명시한 공고만 분모로 삼아** 정규화한 뒤 비교한다.

실행:
  python src/analyze_hn_seniority.py
"""

import glob
import json
import os
import re
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from provenance import DATA_DIR, RAW_DIR  # noqa: E402

# 구직자 글 (채용 공고가 아님)
SEEKING = re.compile(r"\bSEEKING WORK\b", re.I)

# 신입/주니어 수용 신호
ENTRY = re.compile(
    r"\b(entry[- ]level|new[- ]grad(uate)?s?|junior|early[- ]career"
    r"|all (experience )?levels|any level|no experience (is )?(required|necessary)"
    r"|0\s*[-–to]+\s*[12]\s*years?)\b",
    re.I,
)

# 시니어 이상 요구 신호
SENIOR = re.compile(
    r"\b(senior|sr\.?\s|staff engineer|principal|tech lead|team lead"
    r"|[5-9]\+?\s*years|1\d\+?\s*years)\b",
    re.I,
)

# 명시적 최소 연차: "3+ years", "5 to 8 years", "at least 4 years"
MIN_YEARS = re.compile(
    r"(?:at least\s+)?(\d{1,2})\s*\+?\s*(?:[-–]|to)?\s*(?:\d{1,2})?\s*(?:years?|yrs?)"
    r"[^.]{0,25}\bexperience\b",
    re.I,
)


def min_years(text: str) -> int | None:
    """본문에서 최소 요구 연차를 뽑는다. 여러 개면 가장 작은 값."""
    values = [int(m.group(1)) for m in MIN_YEARS.finditer(text)]
    values = [v for v in values if 0 <= v <= 20]  # 20년 초과는 오탐으로 본다
    return min(values) if values else None


def classify(text: str) -> dict:
    entry = bool(ENTRY.search(text))
    senior = bool(SENIOR.search(text))
    return {
        "entry": entry,
        "senior": senior,
        "level_stated": entry or senior,
        "min_years": min_years(text),
    }


def main() -> None:
    raw_files = sorted(glob.glob(os.path.join(RAW_DIR, "hn_hiring_*.json")))
    if not raw_files:
        raise SystemExit("\n[중단] data/raw/hn_hiring_*.json 없음 "
                         "→ python src/collect_global_hn.py 먼저 실행\n")

    with open(raw_files[-1], "r", encoding="utf-8") as f:
        raw = json.load(f)

    rows, all_years = [], []
    for ym, posts in sorted(raw.items()):
        posts = [p for p in posts if not SEEKING.search(p)]
        if not posts:
            continue

        flags = [classify(p) for p in posts]
        stated = sum(1 for f in flags if f["level_stated"])
        entry = sum(1 for f in flags if f["entry"])
        senior_only = sum(1 for f in flags if f["senior"] and not f["entry"])
        years = [f["min_years"] for f in flags if f["min_years"] is not None]
        all_years.extend(years)

        rows.append({
            "기준월": ym,
            "공고수": len(posts),
            "레벨명시": stated,
            "신입수용": entry,
            "시니어전용": senior_only,
            "신입비중_전체대비": round(entry / len(posts), 4),
            "신입비중_레벨명시대비": round(entry / stated, 4) if stated else None,
            "연차명시": len(years),
            "최소연차_중앙값": pd.Series(years).median() if years else None,
        })

    df = pd.DataFrame(rows)
    out = os.path.join(DATA_DIR, "hn_seniority.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")

    print("=" * 70)
    print("HN 채용글 요구 레벨 분석")
    print("=" * 70 + "\n")

    print(f"분석 대상: {len(df)}개월 / 공고 {df['공고수'].sum():,}건")
    print(f"  레벨 명시: {df['레벨명시'].sum():,}건 "
          f"({df['레벨명시'].sum()/df['공고수'].sum():.1%})")
    print(f"  연차 숫자 명시: {df['연차명시'].sum():,}건 "
          f"({df['연차명시'].sum()/df['공고수'].sum():.1%})")
    if all_years:
        s = pd.Series(all_years)
        print(f"  명시된 최소 연차: 중앙값 {s.median():.0f}년 / 평균 {s.mean():.1f}년")
        print(f"  분포: " + ", ".join(
            f"{y}년 {c}건" for y, c in s.value_counts().sort_index().head(8).items()))

    df["연도"] = df["기준월"].astype(str).str[:4]
    year = df.groupby("연도").agg(
        공고수=("공고수", "sum"), 레벨명시=("레벨명시", "sum"),
        신입수용=("신입수용", "sum"), 시니어전용=("시니어전용", "sum"))
    year["신입비중_레벨명시대비"] = (year["신입수용"] / year["레벨명시"] * 100).round(1)
    year["시니어전용비중"] = (year["시니어전용"] / year["레벨명시"] * 100).round(1)

    print("\n연도별 (분모 = 레벨을 명시한 공고):")
    print(year[["공고수", "레벨명시", "신입비중_레벨명시대비", "시니어전용비중"]].to_string())

    latest = year.iloc[-1]
    print("\n" + "-" * 70)
    print("국내 비교")
    print("-" * 70)
    print(f"  국내 (구조화 필드 annual_from=0): 신입 지원 가능 12.9% (48/373건)")
    print(f"  해외 ({year.index[-1]}, 레벨 명시 공고 대비): "
          f"신입 수용 {latest['신입비중_레벨명시대비']:.1f}%")
    print("\n  ※ 국내는 모든 공고가 연차 필드를 가지지만, HN은 레벨을 명시한 공고가")
    print(f"     전체의 {df['레벨명시'].sum()/df['공고수'].sum():.0%}뿐이다.")
    print("     따라서 '레벨을 밝힌 공고 중 신입을 받는 비율'로 정규화해 비교했다.")

    print(f"\n저장: data/hn_seniority.csv")


if __name__ == "__main__":
    main()
