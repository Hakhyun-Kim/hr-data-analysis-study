# HR 데이터 분석 스터디

**채용·고용 데이터**를 직접 수집하고 검증하면서 배운 것을 정리한 저장소입니다.

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
| 좁아진 것은 **민간 쪽이다** | 공공 IT·정규직 신입 가능 **88.6%** (6년간 유지) | 잡알리오 |
| 하락은 **직군별로 고르지 않다** | 프론트엔드 -36% vs 백엔드 -13% (시장 대비) | Hacker News |

➔ 문제는 "채용 한파"가 아니라 **"진입문 축소 + 요구 역량 이동"** 이었습니다.

![신입 진입문 비교](docs/figures/entry_level_comparison.png)

직군별로 갈라 보면 하락이 고르지 않습니다. 프론트엔드는 고점 대비 3분의 1로 줄었는데
백엔드·풀스택은 버텼습니다.

![직군별 채용 수요](docs/figures/role_demand_trend.png)

---

## 📁 목차

| 문서 | 내용 |
| :--- | :--- |
| [01. 데이터 소스 접근성 조사](docs/01-data-source-access.md) | 개인 계정으로 어디까지 받을 수 있나 — 실패 기록 포함 |
| [02. 국내 채용 시장 분석](docs/02-domestic-analysis.md) | KOSIS + 국민연금 + JD 텍스트 + 공공부문(잡알리오) |
| [03. 해외 트렌드 분석](docs/03-global-trend.md) | Hacker News 시계열 + 직군별 수요 + Greenhouse 교차 검증 |
| [04. 이번 스터디에서 배운 것](docs/04-lessons.md) | **가장 값진 부분 — 데이터를 믿기 전에 의심하는 법** |

---

## 🗂️ 데이터 소스

| 소스 | 인증 | 사용 여부 |
| :--- | :--- | :--- |
| KOSIS 국가통계포털 | API 키 (무료, 즉시) | ✅ 산업별 취업자 78개월 |
| 공공데이터포털 국민연금 | API 키 (무료, 자동승인) | ✅ 기업별 가입자·입퇴사 |
| 잡알리오 공공기관 채용 | API 키 (무료, 자동승인) | ✅ 공고 86,635건 / 80개월 |
| Hacker News (Algolia) | **불필요** | ✅ 채용글 39,831건 |
| Greenhouse 채용 보드 | **불필요** | ✅ 31개사 개발 JD 2,860건 |
| 국내 채용 플랫폼 공개 API | 불필요 | ✅ JD 373건 |
| 워크넷(고용24) | 기업회원 전용 | ❌ 개인 접근 불가 |
| EIS 고용행정통계 | 불필요하나 IP 일일 쿼터 | ❌ 시계열 수집 불가 |

> 수집한 원본 데이터는 재배포하지 않습니다(`data/`는 gitignore). 아래 스크립트로 직접 수집할 수 있습니다.

---

## ⚙️ 실행

### 1. 환경 준비

Python 3.10 이상이 필요합니다.

```bash
python -m venv .venv
```

```bash
.venv\Scripts\activate
```

```bash
pip install requests pandas matplotlib wordcloud
```

> macOS·Linux에서는 `source .venv/bin/activate` 를 쓰고, `src/visualize.py` 의 `FONT_PATH`
> (기본값 `C:/Windows/Fonts/malgun.ttf`)를 시스템에 있는 한글 폰트 경로로 바꿔야 합니다.
> 이 값이 없으면 그래프의 한글이 깨지고 워드클라우드는 폰트를 못 찾아 실패합니다.

### 2. API 키 발급

| 환경변수 | 발급처 | 절차 | 승인 |
| :--- | :--- | :--- | :--- |
| `KOSIS_API_KEY` | [kosis.kr/openapi](https://kosis.kr/openapi) | 회원가입 → 활용신청 | 즉시 |
| `DATA_GO_KR_SERVICE_KEY` | [data.go.kr](https://www.data.go.kr) → `국민연금공단_국민연금 가입 사업장 내역` 검색 → 활용신청 | 자동승인 | 즉시 |
| `WORKNET_API_KEY` | [work24.go.kr](https://www.work24.go.kr) → 오픈API 활용신청 | **기업(사업자) 회원 전용** | 개인 계정 거부 |

* 셋 다 무료입니다. 워크넷 키는 개인 계정으로 발급받아도 호출이 거부되므로 **없어도 됩니다**
  (`--source worknet` 은 거부 사실을 기록하는 용도입니다).
* 공공데이터포털 키는 Encoding/Decoding 두 벌을 주는데 **어느 쪽을 넣어도 됩니다**.
  `%` 가 들어 있으면 스크립트가 자동으로 디코딩해서 보냅니다.
* 승인 직후에는 키가 서버에 반영되기까지 시간이 걸릴 수 있습니다(포털 안내 기준 최대 1시간).

### 3. 키 입력

```bash
copy .env.example .env
```

`.env` 를 열어 `=` 뒤에 발급받은 키를 붙여넣습니다. 따옴표는 붙이지 않습니다.

```
KOSIS_API_KEY=여기에키
DATA_GO_KR_SERVICE_KEY=여기에키
```

`.env` 는 `.gitignore` 대상이라 커밋되지 않습니다. 키를 코드나 문서에 직접 쓰지 마세요.
키가 비어 있으면 스크립트는 **대체값을 만들지 않고 즉시 중단**하며, 발급 방법과 입력 위치를 출력합니다.

### 4. 수집 → 분석 → 시각화

각 단계는 `data/` 에 결과를 쓰고, 수집 이력을 `data/provenance.json` 에 남깁니다.

| # | 명령 | 필요한 키 | 산출물 |
| :-- | :--- | :--- | :--- |
| 1 | `python src/check_public_api.py --source kosis` | KOSIS | `data/kosis_employment.csv` |
| 2 | `python src/collect_global_hn.py --start 202001` | **불필요** | `data/global_hn_hiring.csv` |
| 3 | `python src/collect_greenhouse.py --dev-only` | **불필요** | `data/global_greenhouse_jobs.json` / `.csv` |
| 4 | `python src/collect_alio.py --start 20200101` | 공공데이터포털 | `data/alio_recruitment.csv` / `alio_monthly.csv` |
| 5 | `python src/collect_nps_companies.py` | 공공데이터포털 | `data/nps_companies.csv` |
| 6 | `python src/analysis.py` | — | 콘솔 리포트 (결론 수치) |
| 7 | `python src/analyze_hn_seniority.py` | — | `data/hn_seniority.csv` |
| 8 | `python src/compare_entry_level.py` | — | 콘솔 리포트 (공공/민간/해외 신입 비교) |
| 9 | `python src/analyze_role_demand.py` | — | 콘솔 리포트 (직군별 수요 변화) |
| 10 | `python src/visualize.py` | — | `docs/figures/*.png` |

```bash
python src/check_public_api.py --source kosis
```

```bash
python src/collect_global_hn.py --start 202001
```

```bash
python src/collect_greenhouse.py --dev-only
```

```bash
python src/collect_alio.py --start 20200101
```

```bash
python src/collect_alio.py --start 20200101 --it-only --regular-only
```

```bash
python src/collect_nps_companies.py
```

```bash
python src/analysis.py
```

```bash
python src/analyze_hn_seniority.py
```

```bash
python src/compare_entry_level.py
```

```bash
python src/analyze_role_demand.py
```

```bash
python src/visualize.py
```

주요 옵션

* `check_public_api.py` — `--source kosis|nps|worknet|all`, `--start/--end YYYYMM`,
  `--kosis-table`(기본 `DT_1DA9003S`), `--rows`, `--pages`
* `collect_global_hn.py` — `--start YYYYMM` (2020-01부터 현재까지 월간 채용 스레드)
* `collect_greenhouse.py` — `--dev-only`(개발 직군만), `--game`(게임사 5곳, 별도 파일),
  `--boards a,b,c`, `--tag`, `--skip-missing`
* `collect_alio.py` — `--start YYYYMMDD`(공고 시작일 하한), `--it-only`(NCS 정보통신),
  `--regular-only`(정규직), `--ongoing`, `--max-calls`(일 한도 보호)
* `collect_nps_companies.py` — `--limit N` (기업 수 제한, 0=전체)

### 5. 국내 JD 수집분에 대해

5·6·8·10단계는 `data/domestic_jobs.json`(국내 채용 플랫폼 JD)을 입력으로 씁니다.
이 파일을 만드는 수집 스크립트는 **저장소에 포함되어 있지 않습니다.**
따라서 클론 직후 재현되는 범위는 다음과 같습니다.

| 재현 가능 | 재현 불가 |
| :--- | :--- |
| KOSIS 산업별 취업자 추이 | 국내 **민간** JD 스택·연차 분석 |
| 잡알리오 공공기관 채용 86,635건 / 80개월 | 기업별 국민연금 고용 (JD 기업명이 입력) |
| Hacker News 시계열 39,831건 + 요구 레벨 | |
| Greenhouse 해외 기업 JD 2,860건 | |

`domestic_jobs.json` 이 없으면 해당 스크립트는 실행을 중단하고 그 사실을 출력합니다.
키 없이 확인만 하려면 2 → 3 → 7 → 9단계만 돌려도 됩니다.

### 6. 자주 걸리는 것

| 증상 | 원인 |
| :--- | :--- |
| `[중단] ...키를 찾을 수 없습니다` | `.env` 미생성 또는 키 비어 있음 — 3단계 확인 |
| 국민연금 응답이 `totalCount=0` (오류 아님) | 파라미터를 snake_case로 보냄. 이 API는 **camelCase** 필수 |
| 국민연금 인증 실패 | Encoding 키를 그대로 URL에 붙여 이중 인코딩된 경우 |
| EIS 수집 중 `HITS_EXCEEDED` | IP 단위 **일일** 쿼터. 대기해도 안 풀립니다 ([01번 문서](docs/01-data-source-access.md)) |
| 그래프 한글이 □ 로 깨짐 | `FONT_PATH` 가 없는 경로 — 1단계 참고 |

---

## 📂 구조

```
├── src/
│   ├── provenance.py             # 출처 추적 — 원본 보존 + 수집 이력
│   ├── job_dataset.py            # JD 로딩·정제 (분석/그래프 공용)
│   ├── check_public_api.py       # KOSIS / 국민연금 / 워크넷
│   ├── collect_nps_companies.py  # 기업명 매칭 → 고용 데이터
│   ├── collect_global_hn.py      # 해외 채용 시계열
│   ├── collect_greenhouse.py     # 해외 기업 JD 원문 (인증키 불필요)
│   ├── collect_alio.py           # 공공기관 채용 공고 (국내 유일 시계열)
│   ├── collect_eis_vacancy.py    # EIS (쿼터 제한으로 미사용, 기록용)
│   ├── enrich_job_annual.py      # 요구 연차 필드 보강
│   ├── analysis.py               # 통합 분석
│   ├── analyze_hn_seniority.py   # 해외 요구 레벨 파싱
│   ├── compare_entry_level.py    # 신입 진입문 3자 비교 (공공/민간/해외)
│   ├── analyze_role_demand.py    # 직군별 수요 변화 + 키워드 사전 민감도
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

이 분석은 **개인 스터디 결과물**입니다. 다음 한계를 안고 있습니다.

1. **민간 JD는 단면 데이터**입니다. 과거 공고를 받을 수 없어 "국내 민간에서 스택이 이동했다"는 시계열 주장은 하지 못합니다. 국내 시계열은 공공부문(잡알리오)에만 있고, 공공 공고에는 기술 스택이 안 적혀 있어 스택 이동은 해외(HN)로만 볼 수 있습니다.
2. **HN은 스타트업·원격·미국 중심 표본**입니다. 글로벌 전체를 대표하지 않습니다.
3. **세 모집단(공공·민간·해외)은 측정 방식이 다릅니다.** 공공은 기관이 고른 코드값, 민간은 구조화된 연차 필드, HN은 자유 텍스트 파싱입니다. 나란히 놓을 수는 있어도 %p로 빼서 "격차"라고 부르면 안 됩니다.
4. **키워드 매칭은 의미를 구분하지 않습니다.** `Agent`가 "AI Agent"인지 "user agent"인지 구분하지 않습니다. 직군 분류는 사전을 두 벌로 흔들어 결과가 갈리는 항목을 표시했습니다.
5. **Greenhouse 수집분은 현재 열린 공고만**입니다. 마감분이 빠져 생존 편향이 있어 시계열로 쓰지 않았습니다.
6. **게임 클라이언트 수요 변화는 확인하지 못했습니다.** 게임사 공고의 77%가 직무명에 계층을 적지 않고, 공공 통계에도 시계열이 없습니다.

한계를 숨기는 것보다 적어두는 편이 낫다고 생각해 모두 명시했습니다.

---

## 라이선스

코드는 MIT. 분석 내용은 자유롭게 인용하시되 출처만 남겨주세요.
공공데이터(KOSIS·국민연금)는 각 기관의 이용약관을 따릅니다.
