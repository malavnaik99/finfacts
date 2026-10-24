"""Stage (and optionally publish) the FinFacts dataset for Hugging Face.

  uv run python scripts/publish_hf.py           # stage into data/hf/dataset and print a summary
  uv run python scripts/publish_hf.py --upload  # also create/update the PUBLIC dataset repo

Needs HF_TOKEN (write) in .env for --upload. Stages: eval questions + verification, the frozen
certified tables from the eval snapshot, and the embedded 10-K chunks.
"""

import json
import shutil
import sys
from pathlib import Path

import duckdb

from finfacts.eval.snapshot import SNAPSHOT_DATE
from finfacts.settings import Settings

SNAPSHOT = Path("data/eval/finfacts_eval_v1.duckdb")
STAGE = Path("data/hf/dataset")
EVAL = Path("eval/v1")
CHUNKS = Path("data/hf/tenk_chunks.parquet")
TABLES = ["financials", "financials_history", "companies", "metrics"]


def eval_results_markdown() -> str:
    summaries = sorted((EVAL / "results").glob("*/summary.json"))
    if not summaries:
        return "_Not run yet._"
    lines = [
        "| Model | Before (raw XBRL facts) | After (FinFacts semantic layer) |",
        "|---|---|---|",
    ]
    for p in summaries:
        s = json.loads(p.read_text(encoding="utf-8"))
        b, a = s["conditions"]["before"], s["conditions"]["after"]
        lines.append(f"| `{s['model']}` | {b['accuracy']:.1%} | {a['accuracy']:.1%} |")
    return "\n".join(lines) + (
        "\n\nExecution accuracy on all questions: the same model, prompt rules and one repair "
        "attempt; only the schema differs (raw SEC facts vs the certified tables + metric "
        "definitions)."
    )


def stage() -> dict[str, int]:
    shutil.rmtree(STAGE, ignore_errors=True)
    (STAGE / "eval").mkdir(parents=True)
    (STAGE / "tables").mkdir()
    (STAGE / "tenk").mkdir()
    shutil.copy(EVAL / "questions.jsonl", STAGE / "eval" / "questions.jsonl")
    shutil.copy(EVAL / "verification.csv", STAGE / "eval" / "verification.csv")
    counts: dict[str, int] = {}
    with duckdb.connect(str(SNAPSHOT), read_only=True) as con:
        for t in TABLES:
            out = (STAGE / "tables" / f"{t}.parquet").as_posix()
            con.execute(f"copy semantic.{t} to '{out}' (format parquet, compression zstd)")
            counts[t] = con.sql(f"select count(*) from semantic.{t}").fetchone()[0]  # type: ignore[index]  # noqa: S608
        counts["chunks"] = con.sql(f"select count(*) from '{CHUNKS.as_posix()}'").fetchone()[0]  # type: ignore[index]  # noqa: S608
    shutil.copy(CHUNKS, STAGE / "tenk" / "tenk_chunks.parquet")
    qs = [json.loads(line) for line in (EVAL / "questions.jsonl").read_text("utf-8").splitlines()]
    card = (
        Path("eval/hf_README.md")
        .read_text(encoding="utf-8")
        .replace("{snapshot_date}", SNAPSHOT_DATE)
        .replace("{n_questions}", str(len(qs)))
        .replace("{n_template}", str(sum(q["source"] == "template" for q in qs)))
        .replace("{n_hand}", str(sum(q["source"] == "handwritten" for q in qs)))
        .replace("{n_financials}", f"{counts['financials']:,}")
        .replace("{n_history}", f"{counts['financials_history']:,}")
        .replace("{n_companies}", f"{counts['companies']:,}")
        .replace("{n_metrics}", f"{counts['metrics']:,}")
        .replace("{n_chunks}", f"{counts['chunks']:,}")
        .replace("{eval_results}", eval_results_markdown())
    )
    (STAGE / "README.md").write_text(card, encoding="utf-8")
    return counts


def upload() -> str:
    from huggingface_hub import HfApi

    token = Settings().hf_token  # type: ignore[call-arg]
    if not token:
        raise SystemExit("set HF_TOKEN (write) in .env")
    api = HfApi(token=token)
    repo_id = f"{api.whoami()['name']}/finfacts"
    api.create_repo(repo_id, repo_type="dataset", private=False, exist_ok=True)
    api.upload_folder(
        repo_id=repo_id,
        repo_type="dataset",
        folder_path=str(STAGE),
        commit_message=f"FinFacts dataset, snapshot {SNAPSHOT_DATE}",
    )
    return f"https://huggingface.co/datasets/{repo_id}"


if __name__ == "__main__":
    counts = stage()
    size_mb = sum(f.stat().st_size for f in STAGE.rglob("*") if f.is_file()) / 1e6
    print(f"staged {STAGE}: {counts}, {size_mb:.0f} MB")
    if "--upload" in sys.argv:
        print("published:", upload())
