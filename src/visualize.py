"""수집·분석 결과 시각화.

생성물 (docs/figures/)
  1. ict_employment_trend.png   정보통신업 취업자 추이 (KOSIS)
  2. stack_by_category.png      직군별 기술 스택 언급률
  3. stack_by_career.png        연차별 AI 스택 요구율 + 공고 수
  4. company_net_change.png     기업별 고용 순증감 분포 (국민연금)
  5. jd_wordcloud.png           JD 본문 워드클라우드

모든 그림은 정제된 모집단(job_dataset.load_jobs)을 사용해 보고서 수치와 일치시킨다.
"""

import os
import re
import sys
from collections import Counter

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.font_manager as fm  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from wordcloud import WordCloud  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from job_dataset import SW_INDUSTRY, body_text, load_jobs  # noqa: E402
from provenance import DATA_DIR, ROOT  # noqa: E402

FIG_DIR = os.path.join(ROOT, "docs", "figures")
FONT_PATH = "C:/Windows/Fonts/malgun.ttf"

AI_STACK = ["LLM", "RAG", "Agent", "LangChain", "LlamaIndex", "Fine-tuning",
            "Vector DB", "임베딩", "프롬프트"]
CLASSIC_STACK = ["Spring", "Java", "MySQL", "Kubernetes", "Docker", "AWS",
                 "Django", "Node.js"]

PALETTE = {"ai": "#4C6FFF", "classic": "#FF8A3D", "pos": "#2BA84A", "neg": "#D64550",
           "line": "#1F3A93", "grid": "#DDDDDD"}


def setup_font() -> None:
    if os.path.exists(FONT_PATH):
        fm.fontManager.addfont(FONT_PATH)
        plt.rcParams["font.family"] = fm.FontProperties(fname=FONT_PATH).get_name()
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 130
    plt.rcParams["savefig.bbox"] = "tight"


def mentions(text: str, keyword: str) -> bool:
    if keyword.isascii():
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(keyword)}(?![A-Za-z0-9])",
                         text, re.IGNORECASE) is not None
    return keyword in text


def save(fig, name: str) -> None:
    os.makedirs(FIG_DIR, exist_ok=True)
    path = os.path.join(FIG_DIR, name)
    fig.savefig(path)
    plt.close(fig)
    print(f"  저장: docs/figures/{name}")


# ------------------------------------------------------------------ 1
def fig_ict_trend() -> None:
    path = os.path.join(DATA_DIR, "kosis_employment.csv")
    if not os.path.exists(path):
        print("  [건너뜀] kosis_employment.csv 없음")
        return

    df = pd.read_csv(path, encoding="utf-8-sig")
    df["수치값"] = pd.to_numeric(df["수치값"], errors="coerce")
    ict = df[df["분류"] == "J 정보통신업"].sort_values("시점").dropna(subset=["수치값"])
    if ict.empty:
        print("  [건너뜀] 정보통신업 행 없음")
        return

    periods = ict["시점"].astype(str)
    x = range(len(ict))
    fig, ax = plt.subplots(figsize=(11, 4.6))
    ax.plot(x, ict["수치값"], color=PALETTE["line"], linewidth=2.2)
    ax.fill_between(x, ict["수치값"], ict["수치값"].min() * 0.97,
                    color=PALETTE["line"], alpha=0.10)

    peak_idx = int(ict["수치값"].reset_index(drop=True).idxmax())
    peak_val = ict["수치값"].iloc[peak_idx]
    ax.scatter([peak_idx], [peak_val], color=PALETTE["neg"], zorder=5, s=45)
    ax.annotate(f"역대 고점 {peak_val:,.1f}천명\n({periods.iloc[peak_idx]})",
                xy=(peak_idx, peak_val), xytext=(-95, -30),
                textcoords="offset points", fontsize=9, color=PALETTE["neg"])

    step = max(1, len(ict) // 12)
    ax.set_xticks(list(x)[::step])
    ax.set_xticklabels([p[:4] + "." + p[4:] for p in periods][::step], rotation=45, fontsize=8)
    ax.set_ylabel("취업자 (천명)")
    ax.set_title("정보통신업(J) 취업자 추이 — 계절조정, KOSIS DT_1DA9003S", fontsize=12, pad=12)
    ax.grid(axis="y", color=PALETTE["grid"], linewidth=0.7)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    save(fig, "ict_employment_trend.png")


# ------------------------------------------------------------------ 2
def fig_stack_by_category(jobs: list) -> None:
    groups: dict[str, list[str]] = {}
    for job in jobs:
        groups.setdefault(job["structured"]["category"], []).append(body_text(job))

    names = list(groups)
    ai = [sum(1 for t in groups[n] if any(mentions(t, k) for k in AI_STACK)) / len(groups[n])
          for n in names]
    classic = [sum(1 for t in groups[n] if any(mentions(t, k) for k in CLASSIC_STACK)) / len(groups[n])
               for n in names]

    fig, ax = plt.subplots(figsize=(8, 4.4))
    y = range(len(names))
    height = 0.36
    ax.barh([i + height / 2 for i in y], ai, height, label="AI 에이전트 스택",
            color=PALETTE["ai"])
    ax.barh([i - height / 2 for i in y], classic, height, label="전통 백엔드 스택",
            color=PALETTE["classic"])

    for i, (a, c) in enumerate(zip(ai, classic)):
        ax.text(a + 0.012, i + height / 2, f"{a:.1%}", va="center", fontsize=9)
        ax.text(c + 0.012, i - height / 2, f"{c:.1%}", va="center", fontsize=9)

    ax.set_yticks(list(y))
    ax.set_yticklabels([f"{n}\n(N={len(groups[n])})" for n in names], fontsize=9)
    ax.set_xlabel("해당 스택을 1개 이상 언급한 공고 비율")
    ax.set_xlim(0, max(ai + classic) * 1.22)
    ax.set_title("직군별 기술 스택 언급률 — 국내 채용 플랫폼 JD", fontsize=12, pad=12)
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    ax.grid(axis="x", color=PALETTE["grid"], linewidth=0.7)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    save(fig, "stack_by_category.png")


# ------------------------------------------------------------------ 3
def fig_stack_by_career(jobs: list) -> None:
    def bucket(annual_from) -> str | None:
        if annual_from is None:
            return None
        years = int(annual_from)
        if years == 0:
            return "신입\n(0년)"
        if years <= 3:
            return "주니어\n(1~3년)"
        if years <= 7:
            return "미들\n(4~7년)"
        return "시니어\n(8년+)"

    order = ["신입\n(0년)", "주니어\n(1~3년)", "미들\n(4~7년)", "시니어\n(8년+)"]
    groups: dict[str, list[str]] = {}
    for job in jobs:
        name = bucket(job["structured"].get("annual_from"))
        if name:
            groups.setdefault(name, []).append(body_text(job))

    names = [n for n in order if n in groups]
    counts = [len(groups[n]) for n in names]
    ratios = [sum(1 for t in groups[n] if any(mentions(t, k) for k in AI_STACK)) / len(groups[n])
              for n in names]

    fig, ax1 = plt.subplots(figsize=(8.6, 4.6))
    bars = ax1.bar(names, counts, color="#E3E8F5", width=0.62, label="공고 수")
    ax1.set_ylabel("공고 수", color="#7A8194")
    ax1.tick_params(axis="y", colors="#7A8194")
    for bar, count in zip(bars, counts):
        ax1.text(bar.get_x() + bar.get_width() / 2, count + 2, f"{count}건",
                 ha="center", fontsize=9, color="#7A8194")

    ax2 = ax1.twinx()
    ax2.plot(names, ratios, color=PALETTE["ai"], marker="o", linewidth=2.4,
             markersize=8, label="AI 스택 요구율")
    for i, ratio in enumerate(ratios):
        ax2.text(i, ratio + 0.02, f"{ratio:.1%}", ha="center", fontsize=10,
                 color=PALETTE["ai"], fontweight="bold")
    ax2.set_ylabel("AI 스택 요구율", color=PALETTE["ai"])
    ax2.tick_params(axis="y", colors=PALETTE["ai"])
    ax2.set_ylim(0, max(ratios) * 1.35)

    ax1.set_title("연차별 공고 수와 AI 스택 요구율 — 신입 공고는 전체의 12.9%",
                  fontsize=12, pad=12)
    for side in ("top",):
        ax1.spines[side].set_visible(False)
        ax2.spines[side].set_visible(False)
    save(fig, "stack_by_career.png")


# ------------------------------------------------------------------ 4
def fig_company_net_change() -> None:
    path = os.path.join(DATA_DIR, "nps_companies.csv")
    if not os.path.exists(path):
        print("  [건너뜀] nps_companies.csv 없음")
        return

    df = pd.read_csv(path, encoding="utf-8-sig")
    sw = df[df["업종명"].str.contains(SW_INDUSTRY, na=False)]
    sw = sw.dropna(subset=["순증감", "가입자수"])
    if sw.empty:
        print("  [건너뜀] 소프트웨어 업종 행 없음")
        return

    fig, ax = plt.subplots(figsize=(9, 4.8))
    colors = [PALETTE["pos"] if v > 0 else PALETTE["neg"] if v < 0 else "#B9BFCC"
              for v in sw["순증감"]]
    ax.scatter(sw["가입자수"], sw["순증감"], c=colors, alpha=0.72, s=42, edgecolors="none")
    ax.axhline(0, color="#555", linewidth=1)
    ax.set_xscale("log")
    ax.set_xlabel("국민연금 가입자 수 (명, 로그 스케일)")
    ax.set_ylabel("당월 순증감 (입사 - 퇴사)")

    pos = int((sw["순증감"] > 0).sum())
    neg = int((sw["순증감"] < 0).sum())
    flat = int((sw["순증감"] == 0).sum())
    ax.set_title(f"SW·IT {len(sw)}개사의 월간 고용 순증감 — "
                 f"순증 {pos} / 순감 {neg} / 보합 {flat}", fontsize=12, pad=12)

    # 개별 기업을 특정하지 않는다. 이 그림이 말하려는 것은 "규모별로 순증/순감이
    # 갈린다"이지 "어느 회사가 줄었다"가 아니다. 규모 순으로 익명 라벨만 붙인다.
    for i, (_, row) in enumerate(sw.nlargest(3, "가입자수").iterrows()):
        ax.annotate(f"{chr(ord('A') + i)}사 ({int(row['가입자수']):,}명)",
                    xy=(row["가입자수"], row["순증감"]),
                    xytext=(-8, 8), textcoords="offset points", fontsize=8,
                    color="#444", ha="right")
    ax.set_xlim(right=sw["가입자수"].max() * 2.2)

    ax.grid(color=PALETTE["grid"], linewidth=0.7)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    save(fig, "company_net_change.png")


# ------------------------------------------------------------------ 5
# 조사·어미. 긴 것부터 떼어내야 '보유하신'이 '보유'로 정리된다.
SUFFIXES = [
    "보유하신", "있으신", "하시는", "가능한", "활용한", "하신", "하는", "있는", "되는",
    "으로", "에서", "에게", "이나", "이며", "하며", "된", "한", "을", "를", "이", "가",
    "은", "는", "의", "에", "과", "와", "로", "도",
]

STOPWORDS = {
    # 일반 업무 어휘 — 어느 JD에나 나와 변별력이 없다
    "경험", "능력", "역량", "우대", "필수", "자격", "요건", "사항", "업무", "관련",
    "이해", "가능", "활용", "다양", "다양한", "함께", "우리", "수행", "지원", "제공",
    "사용", "적극", "이상", "대한", "통해", "위한", "또는", "분을", "가진", "직접",
    "실제", "경력", "보유", "여러", "때로", "무엇", "그리고", "하지만", "때문", "위해",
    "커뮤니케이션", "커뮤니", "협업", "소통", "성장", "문화", "동료", "조직", "회사",
    # 접미사만 남은 형태 (어간이 2자 미만이라 분리되지 않는 것들)
    "있으신", "있는", "하는", "하신", "되는", "가능한", "보유하신", "하시는", "이런", "그런",
    # 영어 불용어
    "and", "the", "with", "for", "you", "our", "have", "are", "who", "will", "that",
    "this", "from", "your", "work", "team", "experience", "skills", "ability", "or",
    "in", "to", "of", "on", "as", "is", "be", "we", "at", "an", "it", "by", "can",
    "us", "all", "not", "but", "more", "such", "who", "how", "may", "any", "e.g",
}


def normalize_token(token: str) -> str | None:
    """조사·어미를 떼고 불용어를 걸러낸다. 남길 게 없으면 None."""
    if token.isascii():
        low = token.lower().strip(".")
        return None if low in STOPWORDS or len(low) < 2 else token.strip(".")

    for suffix in SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 2:
            token = token[: -len(suffix)]
            break
    return None if len(token) < 2 or token in STOPWORDS else token


def fig_wordcloud(jobs: list) -> None:
    tokens: list[str] = []
    for job in jobs:
        for raw in re.findall(r"[A-Za-z][A-Za-z0-9+#.]{1,}|[가-힣]{2,}", body_text(job)):
            token = normalize_token(raw)
            if token:
                tokens.append(token)

    counts = Counter(tokens)
    if not counts:
        print("  [건너뜀] 워드클라우드 토큰 없음")
        return

    cloud = WordCloud(
        font_path=FONT_PATH, width=1500, height=780, background_color="white",
        colormap="viridis", max_words=120,
        prefer_horizontal=1.0,  # 한글은 세로로 돌리면 판독이 어려워 가로 고정
        relative_scaling=0.45, min_font_size=12,
    ).generate_from_frequencies(counts)

    fig, ax = plt.subplots(figsize=(11, 5.7))
    ax.imshow(cloud, interpolation="bilinear")
    ax.axis("off")
    ax.set_title(f"국내 채용 플랫폼 JD 자격요건·우대사항 워드클라우드 (N={len(jobs)}건)",
                 fontsize=12, pad=10)
    save(fig, "jd_wordcloud.png")


# ------------------------------------------------------------------ 6
def fig_global_trend() -> None:
    path = os.path.join(DATA_DIR, "global_hn_hiring.csv")
    if not os.path.exists(path):
        print("  [건너뜀] global_hn_hiring.csv 없음")
        return

    df = pd.read_csv(path, encoding="utf-8-sig").sort_values("기준월")
    df["기준월"] = df["기준월"].astype(str)
    x = range(len(df))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11.5, 7), sharex=True,
                                   gridspec_kw={"height_ratios": [1, 1.15]})

    # 위: 채용글 수 (시장 온도)
    ax1.bar(x, df["공고수"], color="#B9C4E8", width=0.75)
    peak = int(df["공고수"].idxmax() - df.index[0])
    ax1.annotate(f"고점 {df['공고수'].max()}건\n({df['기준월'].iloc[peak]})",
                 xy=(peak, df["공고수"].max()), xytext=(10, -6),
                 textcoords="offset points", fontsize=9, color="#444")
    ax1.set_ylabel("월간 채용글 수")
    ax1.set_title("Hacker News 'Who is hiring?' — 글로벌 개발 채용 시장 "
                  f"(총 {df['공고수'].sum():,}건 / {len(df)}개월)", fontsize=12, pad=12)
    ax1.grid(axis="y", color=PALETTE["grid"], linewidth=0.7)
    ax1.set_axisbelow(True)

    # 아래: 스택 비율 교차
    ax2.plot(x, df["AI스택_비율"] * 100, color=PALETTE["ai"], linewidth=2.3,
             label="AI 에이전트 스택")
    ax2.plot(x, df["전통스택_비율"] * 100, color=PALETTE["classic"], linewidth=2.3,
             label="전통 백엔드 스택")
    ax2.set_ylabel("해당 스택 언급 공고 비율 (%)")
    ax2.legend(frameon=False, fontsize=9, loc="center left")
    ax2.grid(color=PALETTE["grid"], linewidth=0.7)
    ax2.set_axisbelow(True)

    step = max(1, len(df) // 14)
    ax2.set_xticks(list(x)[::step])
    ax2.set_xticklabels([m[:4] + "." + m[4:] for m in df["기준월"]][::step],
                        rotation=45, fontsize=8)

    for ax in (ax1, ax2):
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    save(fig, "global_hn_trend.png")


# ------------------------------------------------------------------ 7
KOREA_ENTRY_SHARE = 0.129  # 국내 JD 신입 지원 가능 비중 (48/373건)


def fig_entry_comparison() -> None:
    path = os.path.join(DATA_DIR, "hn_seniority.csv")
    if not os.path.exists(path):
        print("  [건너뜀] hn_seniority.csv 없음")
        return

    df = pd.read_csv(path, encoding="utf-8-sig").sort_values("기준월")
    df["기준월"] = df["기준월"].astype(str)
    df = df.dropna(subset=["신입비중_레벨명시대비"])
    x = range(len(df))

    fig, ax = plt.subplots(figsize=(11.5, 4.8))
    ax.plot(x, df["신입비중_레벨명시대비"] * 100, color=PALETTE["ai"],
            linewidth=1.4, alpha=0.45)
    rolling = df["신입비중_레벨명시대비"].rolling(6, min_periods=2).mean() * 100
    ax.plot(x, rolling, color=PALETTE["ai"], linewidth=2.6,
            label="해외(HN) 신입 수용 비중 — 6개월 이동평균")

    ax.axhline(KOREA_ENTRY_SHARE * 100, color=PALETTE["neg"], linestyle="--",
               linewidth=2, label=f"국내 신입 지원 가능 {KOREA_ENTRY_SHARE:.1%} (2026-08 단면)")

    ax.set_ylabel("신입 수용 공고 비중 (%)")
    ax.set_title("신입 진입문 비교 — 국내가 오히려 넓다\n"
                 "분모: 레벨을 명시한 공고 (HN 18,783건 / 국내 373건)",
                 fontsize=12, pad=12)
    ax.legend(frameon=False, fontsize=9, loc="upper right")

    step = max(1, len(df) // 14)
    ax.set_xticks(list(x)[::step])
    ax.set_xticklabels([m[:4] + "." + m[4:] for m in df["기준월"]][::step],
                       rotation=45, fontsize=8)
    ax.set_ylim(0, max(df["신입비중_레벨명시대비"].max() * 100, 16) * 1.15)
    ax.grid(color=PALETTE["grid"], linewidth=0.7)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    save(fig, "entry_level_comparison.png")


# ------------------------------------------------------------------ 8
# 직군별 언급 비중은 월 단위로 보면 표본 변동이 커서 선이 톱니처럼 튄다.
# 3개월 이동평균으로 추세만 남긴다(원계열은 CSV 에 그대로 있다).
ROLE_LINES = {
    "프론트엔드": "#E4572E",
    "백엔드": "#2BA84A",
    "풀스택": "#4C6FFF",
    "인프라/SRE": "#8E6BBF",
    "모바일": "#B0782A",
}
ROLL = 3


def fig_role_demand() -> None:
    path = os.path.join(DATA_DIR, "role_demand_monthly.csv")
    if not os.path.exists(path):
        print("  [건너뜀] role_demand_monthly.csv 없음 → analyze_role_demand.py 먼저 실행")
        return

    df = pd.read_csv(path, encoding="utf-8-sig").sort_values("기준월")
    df["기준월"] = df["기준월"].astype(str)
    x = range(len(df))

    fig, ax = plt.subplots(figsize=(11.5, 5.4))
    ends = []
    for role, color in ROLE_LINES.items():
        col = f"{role}_비중"
        if col not in df.columns:
            continue
        series = (df[col] * 100).rolling(ROLL, min_periods=1).mean()
        ax.plot(x, series, color=color, linewidth=2.2, label=role)
        ends.append([series.iloc[-1], role, color])

    # 선이 5개라 범례만으로는 눈이 못 따라간다. 끝점에 직접 적되,
    # 값이 겹치는 선(인프라/모바일처럼 같은 %)은 라벨이 포개지므로 세로로 벌린다.
    ends.sort()
    for i in range(1, len(ends)):
        gap = ends[i][0] - ends[i - 1][0]
        if gap < 1.2:
            ends[i][0] = ends[i - 1][0] + 1.2
    for y_label, role, color in ends:
        actual = (df[f"{role}_비중"] * 100).rolling(ROLL, min_periods=1).mean().iloc[-1]
        ax.annotate(f"{role} {actual:.0f}%", xy=(len(df) - 1, y_label),
                    xytext=(6, -3), textcoords="offset points", fontsize=9, color=color)

    # 프론트엔드는 고점 대비 반토막인데 백엔드는 버텼다 — 이 그림의 요지라 짚어준다.
    fr = (df["프론트엔드_비중"] * 100).rolling(ROLL, min_periods=1).mean()
    peak = int(fr.idxmax() - fr.index[0])
    ax.scatter([peak], [fr.iloc[peak]], color=ROLE_LINES["프론트엔드"], s=45, zorder=5)
    ax.annotate(f"프론트엔드 고점 {fr.iloc[peak]:.0f}%\n"
                f"({df['기준월'].iloc[peak][:4]}.{df['기준월'].iloc[peak][4:]})"
                f" → 최근 {fr.iloc[-1]:.0f}%",
                xy=(peak, fr.iloc[peak]), xytext=(-14, 34),
                textcoords="offset points", fontsize=8.5,
                color=ROLE_LINES["프론트엔드"],
                arrowprops=dict(arrowstyle="-", color=ROLE_LINES["프론트엔드"],
                                linewidth=0.8, shrinkB=4))

    ax.set_ylabel("해당 직군 언급 공고 비율 (%)")
    ax.set_title("직군별 채용 수요 — Hacker News 채용글 "
                 f"({df['공고수'].sum():,}건 / {len(df)}개월, {ROLL}개월 이동평균)",
                 fontsize=12, pad=12)
    # 범례는 두지 않는다. 끝점 라벨이 이미 선을 식별하고,
    # 범례를 상단에 두면 고점 주석과 겹친다.
    ax.grid(color=PALETTE["grid"], linewidth=0.7)
    ax.set_axisbelow(True)
    ax.set_xlim(-1, len(df) + 9)   # 끝점 라벨이 잘리지 않도록 오른쪽 여백
    ax.set_ylim(top=ax.get_ylim()[1] * 1.14)  # 고점 주석이 선 위에 앉을 자리

    step = max(1, len(df) // 14)
    ax.set_xticks(list(x)[::step])
    ax.set_xticklabels([m[:4] + "." + m[4:] for m in df["기준월"]][::step],
                       rotation=45, fontsize=8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    save(fig, "role_demand_trend.png")


def main() -> None:
    setup_font()
    print("시각화 생성 시작\n")
    jobs, _ = load_jobs(clean=True)
    print()
    fig_ict_trend()
    fig_stack_by_category(jobs)
    fig_stack_by_career(jobs)
    fig_company_net_change()
    fig_wordcloud(jobs)
    fig_global_trend()
    fig_entry_comparison()
    fig_role_demand()
    print(f"\n[완료] docs/figures/ 에 저장")


if __name__ == "__main__":
    main()
