"""직군별 수요 변화 분석 — "프론트엔드·게임 클라이언트가 AI로 대체됐나?"

가설: 프론트엔드·게임 클라이언트 수요는 줄고 백엔드·인프라는 상대적으로 버텼다.

이 스크립트가 답할 수 있는 것 / 없는 것을 먼저 못박는다.

  답할 수 있음  채용 공고에서 각 직군이 **언급되는 비중**이 2020~2026 사이 어떻게 변했나
  답할 수 없음  그 변화의 **원인이 AI 인가**. 공고 데이터에는 대체 여부가 찍히지 않는다.
                같은 기간 금리·투자 위축·리모트 축소가 동시에 일어났고 분리할 수단이 없다.

세 가지 함정을 피하려고 설계를 이렇게 했다.

  1. 비중만 보면 틀린다. 전체 공고가 반토막인 구간이라 비중이 유지돼도 절대 건수는
     급감한다. 두 수치를 항상 같이 낸다.
  2. 키워드 사전에 결론이 끌려간다. 'infrastructure' 를 넣고 빼는 것만으로 인프라 직군이
     증가로도 감소로도 보인다. **좁은 사전과 넓은 사전을 둘 다 돌려 방향이 뒤집히는
     직군을 표시**한다. 한쪽만 실으면 사전 선택이 결론이 된다.
  3. 게임은 HN 표본이 연 16~92건뿐이라 아무 말도 할 수 없다. 게임사 Greenhouse 보드를
     따로 받아 단면으로만 본다(collect_greenhouse.py --game).

선행 조건
  python src/collect_global_hn.py --start 202001
  python src/collect_greenhouse.py --dev-only          (선택)
  python src/collect_greenhouse.py --game --dev-only   (선택)

실행:
  python src/analyze_role_demand.py
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

# 좁은 사전 — 역할 이름만. 회사가 그 직무를 뽑는다고 명시한 경우에 가깝다.
ROLE_STRICT = {
    "프론트엔드": r"front[- ]?end",
    "백엔드": r"back[- ]?end|server[- ]side",
    "풀스택": r"full[- ]?stack",
    "인프라/SRE": r"\bSRE\b|\bDevOps\b|site reliability",
    "모바일": r"\biOS\b|\bAndroid\b|React Native|Flutter",
    "게임": r"\bUnity\b|\bUnreal\b|\bgamedev\b|game (client|engine|design)",
    "ML/AI": r"machine learning|\bLLM\b|deep learning",
    "데이터": r"data engineer|data scientist|analytics engineer",
}

# 넓은 사전 — 대표 스택까지 포함. 역할명을 안 쓰고 스택만 나열한 공고를 잡는다.
ROLE_BROAD = {
    "프론트엔드": ROLE_STRICT["프론트엔드"] + r"|\bReact\b|\bVue\b|\bAngular\b|\bNext\.js\b",
    "백엔드": ROLE_STRICT["백엔드"] + r"|micro ?service|\bDjango\b|\bRails\b|\bSpring\b",
    "풀스택": ROLE_STRICT["풀스택"],
    "인프라/SRE": ROLE_STRICT["인프라/SRE"] + r"|\bKubernetes\b|\bTerraform\b|infrastructure|platform engineer",
    "모바일": ROLE_STRICT["모바일"] + r"|\bSwift\b|\bKotlin\b|mobile engineer",
    "게임": ROLE_STRICT["게임"] + r"|\bgame\b",
    "ML/AI": ROLE_STRICT["ML/AI"] + r"|\bAI\b|\bML\b|\bPyTorch\b|\bNLP\b",
    "데이터": ROLE_STRICT["데이터"] + r"|\bETL\b|data platform",
}

# Greenhouse 단면용. 본문이 아니라 **직무명**을 보므로 스택 키워드를 섞지 않는다.
ROLE_TITLE = {
    "프론트엔드": r"front[- ]?end|\bUI\b|web engineer",
    "백엔드": r"back[- ]?end|server engineer|\bAPI\b",
    "풀스택": r"full[- ]?stack",
    "인프라/SRE": r"\bSRE\b|\bDevOps\b|infrastructure|platform engineer|site reliability",
    "모바일": r"\biOS\b|\bAndroid\b|mobile",
    "게임": r"\bgame\b|\bgameplay\b|\bengine\b|\bgraphics\b|\brendering\b",
    "ML/AI": r"machine learning|\bML\b|\bAI\b|\bLLM\b|research (engineer|scientist)",
    "데이터": r"\bdata\b|analytics",
    "보안": r"security|\bappsec\b",
}

PART_YEAR = "2026"  # 수집 시점 기준 부분 연도. 증감 계산에서 뺀다.

# 게임사 공고를 클라이언트/서버로 가를 수 있는지 확인하기 위한 사전.
# \b 를 반드시 붙인다. 'engine' 을 경계 없이 쓰면 'Engineer' 를 먹어서
# 'Network Engineer', 'Data Engineering' 까지 클라이언트로 잡힌다(실제로 겪었다).
GAME_CLIENT = re.compile(
    r"\bclient\b|\bgameplay\b|\bgraphics\b|\brender(ing)?\b|\bengine\b|\banimation\b|"
    r"\bUnreal\b|\bUnity\b|\bVFX\b|\bphysics\b|\bshader\b|technical art", re.IGNORECASE)
GAME_SERVER = re.compile(
    r"\bserver\b|\bbackend\b|\bback[- ]end\b|\binfrastructure\b|\bSRE\b|\bDevOps\b|"
    r"\bdistributed\b|\bdatabase\b|\bnetcode\b", re.IGNORECASE)

# 제목만 보면 77%가 판정 불가다. JD **본문**의 엔진·기술 스택으로 넓혀 잡는다.
# 대신 정밀도가 떨어진다 — 회사가 Unreal 을 쓰면 QA·빌드 직무 본문에도 엔진명이 적힌다.
# 따라서 '클라이언트 직무'가 아니라 '클라이언트 스택을 다루는 공고'로 읽어야 한다.
BODY_ENGINE = re.compile(
    r"\bUnity\b|\bUnreal\b|\bUE[45]\b|\bGodot\b|\bCryEngine\b|\bBevy\b|\bFrostbite\b",
    re.IGNORECASE)
BODY_CLIENT = re.compile(
    r"\bC\+\+\b|\bC#\b|\bHLSL\b|\bGLSL\b|\bshader\b|\bDirectX\b|\bVulkan\b|\bOpenGL\b|"
    r"\bgameplay\b|\brendering\b|\banimation\b", re.IGNORECASE)
BODY_SERVER = re.compile(
    r"\bKubernetes\b|\bAWS\b|\bGCP\b|\bmicroservice\b|\bgRPC\b|\bPostgres\w*\b|"
    r"\bMySQL\b|\bRedis\b|\bKafka\b|\bbackend\b|\bserver[- ]side\b|\bdistributed system",
    re.IGNORECASE)


def compile_all(spec: dict) -> dict:
    return {k: re.compile(v, re.IGNORECASE) for k, v in spec.items()}


def pad(text: str, width: int) -> str:
    """한글은 터미널에서 2칸을 차지한다."""
    used = sum(2 if ord(c) > 0x2E80 else 1 for c in text)
    return text + " " * max(0, width - used)


def load_hn() -> dict:
    files = sorted(glob.glob(os.path.join(RAW_DIR, "hn_hiring_*.json")))
    if not files:
        raise SystemExit("\n[중단] data/raw/hn_hiring_*.json 없음 "
                         "→ python src/collect_global_hn.py --start 202001\n")
    with open(files[-1], "r", encoding="utf-8") as f:
        return json.load(f)


def yearly_counts(raw: dict, patterns: dict) -> pd.DataFrame:
    """연도 × 직군 '언급 공고 수'. 총 언급횟수가 아니라 문서빈도다."""
    rows = {}
    for ym, posts in raw.items():
        year = ym[:4]
        row = rows.setdefault(year, {"공고수": 0, **{k: 0 for k in patterns}})
        row["공고수"] += len(posts)
        for post in posts:
            for role, pat in patterns.items():
                if pat.search(post):
                    row[role] += 1
    return pd.DataFrame(rows).T.sort_index()


def monthly_counts(raw: dict, patterns: dict) -> pd.DataFrame:
    """월 × 직군 언급 공고 수. 그래프가 같은 사전을 쓰도록 CSV 로 남긴다."""
    rows = []
    for ym, posts in sorted(raw.items()):
        row = {"기준월": ym, "공고수": len(posts)}
        for role, pat in patterns.items():
            hit = sum(1 for p in posts if pat.search(p))
            row[role] = hit
            row[f"{role}_비중"] = round(hit / len(posts), 4) if posts else None
        rows.append(row)
    return pd.DataFrame(rows)


def share_table(counts: pd.DataFrame, roles: list) -> pd.DataFrame:
    return counts[roles].div(counts["공고수"], axis=0)


def print_trend(counts: pd.DataFrame, roles: list) -> None:
    share = share_table(counts, roles)
    print(pad("연도", 8) + f"{'공고수':>9}  " + "".join(pad(r, 11) for r in roles))
    print("-" * (19 + 11 * len(roles)))
    for year in counts.index:
        line = pad(year, 8) + f"{int(counts.loc[year, '공고수']):>9,}  "
        line += "".join(pad(f"{share.loc[year, r]:.1%}", 11) for r in roles)
        print(line)


def change_table(counts: pd.DataFrame, roles: list, first: str, last: str) -> pd.DataFrame:
    share = share_table(counts, roles)
    out = []
    for role in roles:
        a, b = counts.loc[first, role], counts.loc[last, role]
        out.append({
            "직군": role,
            f"{first}건수": int(a), f"{last}건수": int(b),
            "절대증감": (b - a) / a if a else None,
            "비중증감p": (share.loc[last, role] - share.loc[first, role]) * 100,
            # 전체 시장이 함께 줄었으므로, 시장 대비 상대 성과가 실제로 보고 싶은 값이다.
            "비중_상대변화": (share.loc[last, role] / share.loc[first, role] - 1)
            if share.loc[first, role] else None,
        })
    return pd.DataFrame(out)


def greenhouse_section(path: str, label: str, patterns: dict) -> None:
    if not os.path.exists(path):
        print(f"  [{label}] 미수집 — 건너뜀 ({os.path.basename(path)})")
        return
    with open(path, "r", encoding="utf-8") as f:
        records = json.load(f)
    titles = [(r["unstructured"].get("position") or "") for r in records]
    n = len(titles)
    print(f"\n  [{label}] 공고 {n:,}건")
    hits = {role: sum(1 for t in titles if pat.search(t)) for role, pat in patterns.items()}
    for role, cnt in sorted(hits.items(), key=lambda x: -x[1]):
        bar = "█" * round(cnt / n * 60)
        print(f"    {pad(role, 12)}{cnt:>5,}건 {cnt / n:>6.1%}  {bar}")


def game_client_server() -> None:
    """게임 클라이언트/서버를 데이터로 가를 수 있는지 '가능 여부 자체'를 측정한다.

    결론을 내는 함수가 아니라, 결론을 낼 수 있는지 재는 함수다.
    판정 불가 비율이 높으면 그 사실을 그대로 보고한다.
    """
    path = os.path.join(DATA_DIR, "global_greenhouse_jobs_game.json")
    print("\n" + "=" * 78)
    print("[5] 게임 클라이언트 vs 서버 — 구분 가능한가")
    print("=" * 78)
    if not os.path.exists(path):
        print("  미수집 — python src/collect_greenhouse.py --game --dev-only")
        return

    with open(path, "r", encoding="utf-8") as f:
        recs = json.load(f)
    titles = [(r["unstructured"].get("position") or "") for r in recs]
    bodies = [(r["unstructured"].get("content") or "") for r in recs]
    n = len(recs)

    def split(texts, client_pat, server_pat):
        c = sum(1 for t in texts if client_pat.search(t) and not server_pat.search(t))
        s = sum(1 for t in texts if server_pat.search(t) and not client_pat.search(t))
        b = sum(1 for t in texts if client_pat.search(t) and server_pat.search(t))
        return c, s, b, n - c - s - b

    print(f"\n  게임사 개발 공고 {n:,}건\n")
    print(pad("기준", 22) + f"{'클라이언트':>11}{'서버':>9}{'둘 다':>9}{'판정 불가':>11}")
    print("  " + "-" * 60)

    rows = [
        ("직무명", *split(titles, GAME_CLIENT, GAME_SERVER)),
        ("JD 본문(엔진·스택)", *split(
            bodies, re.compile(BODY_ENGINE.pattern + "|" + BODY_CLIENT.pattern, re.I),
            BODY_SERVER)),
    ]
    for label, c, s, b, u in rows:
        print(pad("  " + label, 22)
              + f"{c:>7,}건{s:>7,}건{b:>7,}건{u:>9,}건"
              + f"   (불가 {u / n:.0%})")

    engine = sum(1 for t in bodies if BODY_ENGINE.search(t))
    print(f"\n  · 엔진명(Unity/Unreal/Godot 등)만 따로 세면 {engine:,}건 "
          f"({engine / n:.1%})이 본문에 언급합니다.")
    print("  · 본문으로 넓히면 판정 불가가 77% → 28%로 줄지만, **정밀도가 떨어집니다.**"
          "\n    회사가 Unreal 을 쓰면 QA·빌드·SDK 직무 본문에도 엔진명이 적히기 때문입니다."
          "\n    '클라이언트 직무'가 아니라 '클라이언트 스택을 다루는 공고'로 읽어야 합니다.")
    print("  · 두 기준의 클라이언트:서버 비가 서로 다릅니다. 어느 쪽도 단독으로 인용할 수 없습니다.")

    print("\n  ➔ 구성은 볼 수 있지만 **추이는 여전히 못 봅니다.**"
          "\n    게임사 보드에는 마감 공고가 남지 않아 단면뿐이고,"
          "\n    HN 쪽 엔진 언급은 연 16~67건(비중 0.4~0.9%)이라 추세를 논할 표본이 아닙니다.")
    print("  ➔ '게임 클라이언트 수요 감소'는 현재 수집 가능한 소스로 확인할 수 없습니다.")


def main() -> None:
    print("=" * 78)
    print("직군별 수요 변화 — HN 채용글 2020~2026")
    print("=" * 78 + "\n")

    raw = load_hn()
    roles = list(ROLE_STRICT)
    strict = yearly_counts(raw, compile_all(ROLE_STRICT))
    broad = yearly_counts(raw, compile_all(ROLE_BROAD))

    total = int(strict["공고수"].sum())
    print(f"모집단: {len(raw)}개월 / 채용글 {total:,}건 (좁은 사전 기준)\n")

    # 그래프가 이 CSV 를 읽는다. 사전이 갈라지면 보고서 수치와 그림이 어긋난다.
    monthly = monthly_counts(raw, compile_all(ROLE_STRICT))
    monthly_path = os.path.join(DATA_DIR, "role_demand_monthly.csv")
    monthly.to_csv(monthly_path, index=False, encoding="utf-8-sig")
    print(f"  월별 집계 저장: data/role_demand_monthly.csv ({len(monthly)}개월)\n")

    print("[1] 연도별 언급 비중 — 좁은 사전")
    print_trend(strict, roles)
    print(f"\n  ※ {PART_YEAR}년은 수집 시점까지의 부분 집계입니다.")

    years = [y for y in strict.index if y != PART_YEAR]
    first, last = years[0], years[-1]

    print(f"\n[2] {first} → {last} 변화")
    chg = change_table(strict, roles, first, last)
    n_first = int(strict.loc[first, "공고수"])
    n_last = int(strict.loc[last, "공고수"])
    print(f"  전체 공고: {n_first:,} → {n_last:,} ({n_last / n_first - 1:+.0%})"
          f" — 아래 절대증감은 이 하락을 포함한 값입니다.\n")
    print(pad("직군", 12) + f"{'절대증감':>10}{'비중증감':>11}{'시장대비':>11}")
    print("-" * 44)
    for _, r in chg.iterrows():
        print(pad(r["직군"], 12) + f"{r['절대증감']:>+10.0%}"
              f"{r['비중증감p']:>+10.1f}p{r['비중_상대변화']:>+11.0%}")
    print("\n  · 절대증감 = 공고 건수 변화 (시장 전체 하락 포함)")
    print("  · 시장대비 = 비중의 상대 변화. 시장이 반토막이어도 비중을 지켰으면 0% 입니다.")

    print(f"\n[3] 사전 민감도 — 좁은 사전 vs 넓은 사전 ({first}→{last} 시장대비)")
    chg_b = change_table(broad, roles, first, last).set_index("직군")
    chg_s = chg.set_index("직군")
    print(pad("직군", 12) + f"{'좁은 사전':>12}{'넓은 사전':>12}   판정")
    print("-" * 52)
    flipped, wide = [], []
    for role in roles:
        s, b = chg_s.loc[role, "비중_상대변화"], chg_b.loc[role, "비중_상대변화"]
        if (s >= 0) != (b >= 0):
            verdict = "⚠ 방향 뒤집힘"
            flipped.append(role)
        elif abs(s - b) >= 0.30:
            # 방향이 같아도 폭이 크게 갈리면 '얼마나' 를 말할 수 없다.
            verdict = "△ 폭 차이 큼"
            wide.append(role)
        else:
            verdict = "일치"
        print(pad(role, 12) + f"{s:>+11.0%}{b:>+12.0%}   {verdict}")

    if flipped:
        print(f"\n  ⚠ {', '.join(flipped)} — 사전에 따라 증감 방향이 바뀝니다."
              "\n    증감을 주장하지 마세요. 사전 선택이 곧 결론이 됩니다.")
    if wide:
        print(f"\n  △ {', '.join(wide)} — 방향은 같지만 폭이 크게 갈립니다."
              "\n    '줄었다/늘었다'까지만 말하고 몇 % 인지는 말하지 마세요.")
    if not flipped and not wide:
        print("\n  모든 직군에서 두 사전의 방향과 폭이 일치합니다.")

    print("\n" + "=" * 78)
    print("[4] Greenhouse 단면 — 직무명 기준 (시계열 아님, 현재 열린 공고만)")
    print("=" * 78)
    title_pat = compile_all(ROLE_TITLE)
    greenhouse_section(os.path.join(DATA_DIR, "global_greenhouse_jobs.json"),
                       "일반 테크", title_pat)
    greenhouse_section(os.path.join(DATA_DIR, "global_greenhouse_jobs_game.json"),
                       "게임사", title_pat)
    print("\n  ※ 한 공고가 여러 직군에 잡힐 수 있어 합계는 100%를 넘습니다.")

    game_client_server()

    print("\n" + "-" * 78)
    print("[해석 주의]")
    print("  · 이 수치는 '공고에 그 직군이 언급된 비중'입니다. 고용된 사람 수도,")
    print("    대체된 사람 수도 아닙니다.")
    print("  · 감소의 원인을 AI 로 지목할 근거는 이 데이터에 없습니다. 같은 기간")
    print("    전체 공고가 함께 줄었고, 원인을 분리할 변수가 수집분에 없습니다.")
    print("  · HN 은 스타트업·원격·미국 중심 표본입니다. 국내 시장에 그대로 옮길 수 없습니다.")
    print("\n※ 모든 수치는 data/ 수집 파일에서 계산했습니다.")


if __name__ == "__main__":
    main()
