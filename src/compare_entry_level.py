"""신입 진입문 3자 비교 — 공공(잡알리오) vs 민간 국내 vs 해외(HN).

'신입 지원 가능 공고 12.9%' 는 이 스터디의 핵심 수치지만 비교 대상이 해외(HN) 하나뿐이었다.
잡알리오를 IT 직무·정규직으로 좁히면 **같은 나라, 같은 직군, 같은 시점**의 공공부문
기준선이 생긴다. 민간 수치가 낮은 것이 '한국이라서'인지 '민간이라서'인지 갈라볼 수 있다.

⚠ 세 숫자는 측정 방식이 다르다. 나란히 놓되 뺄셈을 하면 안 된다.

  공공  recrutSe 코드값 (R2010 신입 / R2030 신입+경력) — 기관이 직접 선택한 값
  민간  annual_from == 0 (구조화 필드) — 플랫폼이 강제하는 입력값
  해외  JD 자유 텍스트 파싱 (analyze_hn_seniority.py) — 추정값

  특히 공공은 '신입+경력' 통합 공고가 많아 신입 가능 비중이 구조적으로 높게 나온다.
  민간 데이터에는 이에 대응하는 구분이 없다. 이 차이는 정규화로 없앨 수 없어 그대로 둔다.

선행 조건
  python src/collect_alio.py --start 20200101 --it-only --regular-only

실행:
  python src/compare_entry_level.py
"""

import os
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from analysis import career_bucket  # noqa: E402  (판정 규칙을 한 곳에서만 정의한다)
from job_dataset import load_jobs  # noqa: E402
from provenance import DATA_DIR  # noqa: E402

ALIO_IT_REGULAR = "alio_recruitment_R600020_R1010.csv"
ENTRY_OPEN = ("R2010", "R2030")


def pad(text: str, width: int) -> str:
    """한글은 터미널에서 2칸을 차지한다. f-string 의 폭 지정만으로는 표가 어긋난다."""
    used = sum(2 if ord(c) > 0x2E80 else 1 for c in text)
    return text + " " * max(0, width - used)


def load_public() -> pd.DataFrame:
    path = os.path.join(DATA_DIR, ALIO_IT_REGULAR)
    if not os.path.exists(path):
        raise SystemExit(
            f"\n[중단] data/{ALIO_IT_REGULAR} 없음"
            "\n       python src/collect_alio.py --start 20200101 --it-only --regular-only\n")
    df = pd.read_csv(path, encoding="utf-8-sig", dtype={"pbancBgngYmd": str})
    df["연도"] = df["pbancBgngYmd"].str[:4]
    df["신입가능"] = df["recrutSe"].isin(ENTRY_OPEN)
    return df


def public_stat(df: pd.DataFrame) -> dict:
    n = len(df)
    return {
        "n": n,
        "신입가능": int(df["신입가능"].sum()),
        "비중": df["신입가능"].mean(),
        "신입단독": int((df["recrutSe"] == "R2010").sum()),
        "기간": (df["pbancBgngYmd"].min()[:6], df["pbancBgngYmd"].max()[:6]),
    }


def private_stat() -> dict:
    jobs, _ = load_jobs(verbose=False)
    buckets = [career_bucket(j["structured"].get("annual_from")) for j in jobs]
    entry = sum(1 for b in buckets if b == "신입 (0년)")
    return {"n": len(jobs), "신입가능": entry, "비중": entry / len(jobs)}


def global_stat() -> dict | None:
    path = os.path.join(DATA_DIR, "hn_seniority.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, encoding="utf-8-sig", dtype={"기준월": str}).sort_values("기준월")
    stated, entry = int(df["레벨명시"].sum()), int(df["신입수용"].sum())
    last = df.iloc[-1]
    return {
        "n": int(df["공고수"].sum()),
        "레벨명시": stated,
        "신입가능": entry,
        # 전 기간 누적 비중. 보고서 본문의 7.8%는 특정 월 값이라 자릿수가 다르다.
        "비중": entry / stated if stated else None,
        "최근월": (last["기준월"], last["신입비중_레벨명시대비"]),
        "기간": (df["기준월"].min(), df["기준월"].max()),
    }


def main() -> None:
    print("=" * 74)
    print("신입 진입문 비교 — 공공(잡알리오 IT·정규직) / 민간 국내 / 해외(HN)")
    print("=" * 74 + "\n")

    pub = public_stat(load_public())
    pri = private_stat()
    glo = global_stat()

    print(pad("구분", 24) + f"{'모집단':>9}{'신입가능':>10}{'비중':>9}   측정 방식")
    print("-" * 74)
    print(pad("공공 IT·정규직", 24) + f"{pub['n']:>9,}{pub['신입가능']:>10,}"
          f"{pub['비중']:>9.1%}   recrutSe 코드값")
    print(pad("민간 국내 개발 JD", 24) + f"{pri['n']:>9,}{pri['신입가능']:>10,}"
          f"{pri['비중']:>9.1%}   annual_from 구조화 필드")
    if glo:
        print(pad("해외 HN (레벨명시분)", 24) + f"{glo['레벨명시']:>9,}{glo['신입가능']:>10,}"
              f"{glo['비중']:>9.1%}   자유 텍스트 파싱")
    else:
        print(pad("해외 HN", 24) + f"{'미수집':>9}{'—':>10}{'—':>9}"
              "   python src/analyze_hn_seniority.py 먼저 실행")

    print(f"\n  공공 기간 {pub['기간'][0]}~{pub['기간'][1]}"
          + (f" / 해외 기간 {glo['기간'][0]}~{glo['기간'][1]}" if glo else "")
          + " / 민간은 수집 시점 단면")
    if glo:
        # 보고서 본문의 '해외 7.8%'는 최근 1개월 값이다. 위 표는 전 기간 누적이라
        # 같은 지표의 다른 집계다. 둘을 섞어 쓰면 수치가 어긋난 것처럼 보인다.
        ym, ratio = glo["최근월"]
        print(f"  해외 비중은 전 기간 누적입니다. 최근월({ym}) 기준은 {ratio:.1%} 입니다.")

    print("\n" + "-" * 74)
    print("[해석 가능한 것]")
    if pub["비중"] > pri["비중"]:
        print(f"  · 같은 나라·같은 IT 직군인데 공공 {pub['비중']:.1%} vs 민간 {pri['비중']:.1%}."
              f"\n    민간 신입 공고가 적은 것은 '한국이라서'가 아니라 '민간이라서'에 가깝습니다.")
    if glo and pri["비중"] > glo["비중"]:
        print(f"  · 민간 국내 {pri['비중']:.1%} > 해외 HN {glo['비중']:.1%} — 기존 결론 유지.")

    print("\n[해석하면 안 되는 것]")
    print(f"  · 공공 {pub['비중']:.1%} 중 신입 단독 공고는 {pub['신입단독']:,}건"
          f"({pub['신입단독'] / pub['n']:.1%})뿐이고 나머지는 '신입+경력' 통합 공고입니다.")
    print("  · 민간 데이터에는 '신입+경력' 구분 자체가 없어 같은 잣대로 잰 값이 아닙니다.")
    print("  · 세 수치의 차이를 %p 로 빼서 '격차'라고 부르면 측정 방식 차이를 실체로 오인합니다.")

    print("\n" + "-" * 74)
    print("[공공 IT·정규직 연도별] — 국내 데이터 중 유일한 시계열")
    df = load_public()
    yearly = (df.groupby("연도")
                .agg(공고수=("recrutPblntSn", "count"), 신입가능=("신입가능", "sum"))
                .reset_index())
    yearly["비중"] = yearly["신입가능"] / yearly["공고수"]
    for _, r in yearly.iterrows():
        bar = "█" * round(r["비중"] * 40)
        print(f"  {r['연도']}  공고 {r['공고수']:>4,}  신입가능 {r['비중']:>6.1%}  {bar}")
    print("\n  ※ 마지막 연도는 부분 집계입니다(수집 시점까지).")

    print("\n※ 모든 수치는 data/ 수집 파일에서 계산했습니다. 출처는 data/provenance.json 참조.")


if __name__ == "__main__":
    main()
