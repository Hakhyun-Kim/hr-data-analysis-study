# HR 데이터 분석 스터디

한 달 동안 **채용·고용 데이터**를 직접 수집하고 검증하면서 배운 것을 정리한 저장소입니다.

> 📝 **글로 읽기** — [제 보고서의 숫자가 제 데이터랑 달랐습니다](https://hakhyun-kim.github.io/blog/2026-08-10-hr-data-analysis-study/)
> 검증하다 걸려 넘어진 순서대로 풀어 쓴 글입니다. 이 저장소보다 읽기 편합니다.
>
> 🏠 다른 글 — [hakhyun-kim.github.io](https://hakhyun-kim.github.io)

주제는 하나였습니다.

> **"개발자 채용 시장이 얼어붙었다"는 말이 데이터로 사실일까?**

결론부터 말하면 **총량 기준으로는 사실이 아니었고, 다른 곳이 막혀 있었습니다.**

---

## 📊 결론 요약

| 발견 | 근거 | 출처 |
| :--- | :--- | :--- |
| 국내 IT 고용 총량은 **역대 최고** | 정보통신업 취업자 848.7 → 1,185.3천명 (+39.7%) | KOSIS |
| 진짜 병목은 **신입 진입문** | 신입 지원 가능 공고 **12.9%** (48/373건) | 국내 채용 플랫폼 JD |
| 요구 스택이 **직군별로 분화** | AI/데이터 47.7% vs 백엔드 20.0% (27.7%p) | 국내 채용 플랫폼 JD |
| 글로벌은 **스택 이동이 더 뚜렷** | AI 스택 언급 1.5%(2020) → 19.0%(2026), 12.7배 | Hacker News |
| 글로벌 **채용 물량은 -77%** | 월 934건(2021-11) → 212건(2026-08) | Hacker News |
| **신입 진입문은 한국이 오히려 넓다** | 국내 12.9% vs 해외 7.8% | 교차 분석 |

➔ 문제는 "채용 한파"가 아니라 **"진입문 축소 + 요구 역량 이동"** 이었습니다.

![신입 진입문 비교](docs/figures/entry_level_comparison.png)

---

## 📁 목차

| 문서 | 내용 |
| :--- | :--- |
| [01. 데이터 소스 접근성 조사](docs/01-data-source-access.md) | 개인 계정으로 어디까지 받을 수 있나 — 실패 기록 포함 |
| [02. 국내 채용 시장 분석](docs/02-domestic-analysis.md) | KOSIS + 국민연금 + JD 텍스트 융합 |
| [03. 해외 트렌드 분석](docs/03-global-trend.md) | Hacker News 채용글 39,831건 / 81개월 시계열 |
| [04. 이번 스터디에서 배운 것](docs/04-lessons.md) | **가장 값진 부분 — 데이터를 믿기 전에 의심하는 법** |

---

## 🗂️ 데이터 소스

| 소스 | 인증 | 사용 여부 |
| :--- | :--- | :--- |
| KOSIS 국가통계포털 | API 키 (무료, 즉시) | ✅ 산업별 취업자 78개월 |
| 공공데이터포털 국민연금 | API 키 (무료, 자동승인) | ✅ 기업별 가입자·입퇴사 |
| Hacker News (Algolia) | **불필요** | ✅ 채용글 39,831건 |
| 국내 채용 플랫폼 공개 API | 불필요 | ✅ JD 373건 |
| 워크넷(고용24) | 기업회원 전용 | ❌ 개인 접근 불가 |
| EIS 고용행정통계 | 불필요하나 IP 일일 쿼터 | ❌ 시계열 수집 불가 |

> 수집한 원본 데이터는 재배포하지 않습니다(`data/`는 gitignore). 아래 스크립트로 직접 수집할 수 있습니다.

---

## ⚙️ 실행

```bash
copy .env.example .env
```

API 키를 넣은 뒤:

```bash
python src/check_public_api.py --source kosis
```

```bash
python src/collect_nps_companies.py
```

```bash
python src/collect_global_hn.py --start 202001
```

```bash
python src/analysis.py
```

```bash
python src/analyze_hn_seniority.py
```

```bash
python src/visualize.py
```

---

## 📂 구조

```
├── src/
│   ├── provenance.py             # 출처 추적 — 원본 보존 + 수집 이력
│   ├── job_dataset.py            # JD 로딩·정제 (분석/그래프 공용)
│   ├── check_public_api.py       # KOSIS / 국민연금 / 워크넷
│   ├── collect_nps_companies.py  # 기업명 매칭 → 고용 데이터
│   ├── collect_global_hn.py      # 해외 채용 시계열
│   ├── collect_eis_vacancy.py    # EIS (쿼터 제한으로 미사용, 기록용)
│   ├── enrich_job_annual.py      # 요구 연차 필드 보강
│   ├── analysis.py               # 통합 분석
│   ├── analyze_hn_seniority.py   # 해외 요구 레벨 파싱
│   └── visualize.py              # 그래프 생성
└── docs/
    ├── 01-data-source-access.md
    ├── 02-domestic-analysis.md
    ├── 03-global-trend.md
    ├── 04-lessons.md
    └── figures/
```

---

## ⚠️ 한계

이 분석은 **한 달짜리 스터디 결과물**입니다. 다음 한계를 안고 있습니다.

1. **국내 JD는 단면 데이터**입니다. 과거 공고를 받을 수 없어 "국내에서 스택이 이동했다"는 시계열 주장은 하지 못합니다. 해외(HN)만 시계열이 있습니다.
2. **HN은 스타트업·원격·미국 중심 표본**입니다. 글로벌 전체를 대표하지 않습니다.
3. **국내외 비교는 측정 방식이 다릅니다.** 국내는 구조화된 연차 필드, HN은 자유 텍스트 파싱입니다. 정규화했지만 완전히 같은 것을 재는 것은 아닙니다.
4. **키워드 매칭은 의미를 구분하지 않습니다.** `Agent`가 "AI Agent"인지 "user agent"인지 구분하지 않습니다.

한계를 숨기는 것보다 적어두는 편이 낫다고 생각해 모두 명시했습니다.

---

## 🔗 관련 링크

* **이 스터디를 풀어 쓴 글** — [제 보고서의 숫자가 제 데이터랑 달랐습니다](https://hakhyun-kim.github.io/blog/2026-08-10-hr-data-analysis-study/)
* **블로그** — [hakhyun-kim.github.io/blog](https://hakhyun-kim.github.io/blog)
* **홈** — [hakhyun-kim.github.io](https://hakhyun-kim.github.io)

---

## 라이선스

코드는 MIT. 분석 내용은 자유롭게 인용하시되 출처만 남겨주세요.
공공데이터(KOSIS·국민연금)는 각 기관의 이용약관을 따릅니다.
