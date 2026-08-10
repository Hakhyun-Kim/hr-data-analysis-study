"""기존 수집분(domestic_jobs.json)에 요구 연차 필드를 보강한다.

collect_jobs.py 초기 버전이 annual_from/annual_to 를 저장하지 않았다.
원본 응답(data/raw/domestic_jobs_*.json)에 값이 남아 있으므로, 재수집 없이 job_id 로 조인한다.
재수집하면 공고 목록이 바뀌어 이미 분석한 408건과 모집단이 달라지기 때문에 조인을 택한다.
"""

import glob
import json
import os
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from provenance import DATA_DIR, RAW_DIR  # noqa: E402


def main() -> None:
    jobs_path = os.path.join(DATA_DIR, "domestic_jobs.json")
    if not os.path.exists(jobs_path):
        raise SystemExit("\n[중단] data/domestic_jobs.json 없음\n")

    raw_files = sorted(glob.glob(os.path.join(RAW_DIR, "domestic_jobs_*.json")))
    if not raw_files:
        raise SystemExit("\n[중단] data/raw/domestic_jobs_*.json 없음\n")
    raw_path = raw_files[-1]

    with open(raw_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    annual = {
        d.get("id"): (d.get("annual_from"), d.get("annual_to"))
        for d in raw if d.get("id") is not None
    }

    with open(jobs_path, "r", encoding="utf-8") as f:
        jobs = json.load(f)

    filled, missing = 0, 0
    for job in jobs:
        job_id = job["structured"].get("job_id")
        if job_id in annual:
            job["structured"]["annual_from"], job["structured"]["annual_to"] = annual[job_id]
            filled += 1
        else:
            job["structured"].setdefault("annual_from", None)
            job["structured"].setdefault("annual_to", None)
            missing += 1

    with open(jobs_path, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)

    csv_path = os.path.join(DATA_DIR, "domestic_jobs.csv")
    pd.DataFrame([{**j["structured"], **j["unstructured"]} for j in jobs]).to_csv(
        csv_path, index=False, encoding="utf-8-sig"
    )

    print(f"[완료] {filled}건 보강 / {missing}건 원본 미존재")
    print(f"  원본 참조: {os.path.relpath(raw_path, os.path.dirname(DATA_DIR))}")


if __name__ == "__main__":
    main()
