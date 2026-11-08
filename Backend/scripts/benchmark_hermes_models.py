"""Reproducibly benchmark the candidate Ollama models without pulling them.

This is an opt-in developer utility; normal tests and application startup do
not call Ollama. It uses Ollama's local benchmarking API because the existing
provider-neutral interface intentionally does not expose context sizing,
streaming timing, or Ollama load/eval counters. It does not alter production
provider configuration or Hermes tool validation.

Examples (from repository root)::

    python Backend/scripts/benchmark_hermes_models.py --inventory
    python Backend/scripts/benchmark_hermes_models.py --max-prompts 2

No command in this script downloads a model. Missing candidates are skipped.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "docs" / "dev" / "hermes_model_benchmark_prompts.json"
RESULT_PATH = ROOT / "docs" / "dev" / "hermes_model_benchmark_results.json"
REPORT_PATH = ROOT / "docs" / "dev" / "hermes_model_benchmark_report.md"
CANDIDATES = (
    "hermes3:8b",
    "hermes3:8b-llama3.1-q3_K_M",
    "hermes3:3b",
    "hermes3:3b-llama3.2-q3_K_M",
)
CONTEXT_SIZES = (2048, 4096, 8192)
DEFAULT_URL = "http://localhost:11434"


def runtime_configuration() -> dict[str, Any]:
    """Report only non-secret runtime model settings from environment/.env."""
    values: dict[str, str] = {}
    env_file = ROOT / "Backend" / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key.strip() in {"HERMES_PROVIDER", "LOCAL_HERMES_MODEL", "LOCAL_HERMES_URL"}:
                    values[key.strip()] = value.strip().strip("\"'")
    for key in ("HERMES_PROVIDER", "LOCAL_HERMES_MODEL", "LOCAL_HERMES_URL"):
        if os.getenv(key):
            values[key] = os.environ[key]
    return {
        "provider": values.get("HERMES_PROVIDER", "local"),
        "model": values.get("LOCAL_HERMES_MODEL", "hermes3:8b"),
        "url": values.get("LOCAL_HERMES_URL", DEFAULT_URL),
        "source": "environment/.env overrides plus HermesConfig defaults",
    }


def _request(base_url: str, route: str, payload: dict | None = None, timeout: float = 30):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}{route}",
        data=body,
        headers={"Content-Type": "application/json"} if body is not None else {},
        method="POST" if body is not None else "GET",
    )
    return urllib.request.urlopen(req, timeout=timeout)


def ollama_inventory(base_url: str) -> dict[str, Any]:
    """Read Ollama version, installed tags, metadata, and currently loaded models."""
    inventory: dict[str, Any] = {
        "url": base_url,
        "reachable": False,
        "version": None,
        "models": [],
        "loaded": [],
        "error": None,
        "production_config": runtime_configuration(),
        "disk": {
            "path": str(ROOT),
            "free_bytes": shutil.disk_usage(ROOT).free,
            "total_bytes": shutil.disk_usage(ROOT).total,
        },
    }
    try:
        with _request(base_url, "/api/version") as response:
            inventory["version"] = json.load(response).get("version")
        with _request(base_url, "/api/tags") as response:
            tags = json.load(response).get("models", [])
        try:
            with _request(base_url, "/api/ps") as response:
                inventory["loaded"] = json.load(response).get("models", [])
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        inventory["reachable"] = True
        for tag in tags:
            row = {
                "name": tag.get("name"),
                "size_bytes": tag.get("size"),
                "digest": tag.get("digest"),
                "modified_at": tag.get("modified_at"),
            }
            try:
                with _request(base_url, "/api/show", {"model": tag["name"]}) as response:
                    details = json.load(response)
                row["details"] = details.get("details", {})
                model_info = details.get("model_info", {})
                row["quantization"] = row["details"].get("quantization_level")
                row["architecture"] = row["details"].get("family")
                row["parameter_size"] = row["details"].get("parameter_size")
                row["model_info"] = {
                    key: value
                    for key, value in model_info.items()
                    if "context_length" in key or "file_type" in key
                }
            except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError) as exc:
                row["metadata_error"] = str(exc)
            inventory["models"].append(row)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        inventory["error"] = f"{type(exc).__name__}: {exc}"
    return inventory


def runtime_memory() -> dict[str, Any]:
    """Best-effort Ollama process RSS, without adding a dependency."""
    if platform.system() == "Windows":
        try:
            import ctypes
            from ctypes import wintypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.dwLength = ctypes.sizeof(status)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            system = {
                "total_bytes": status.ullTotalPhys,
                "available_bytes": status.ullAvailPhys,
                "used_bytes": status.ullTotalPhys - status.ullAvailPhys,
            }
        except Exception as exc:  # pragma: no cover - machine dependent
            system = {"error": str(exc)}
    else:
        system = {"note": "System memory snapshot not implemented on this platform."}

    processes = []
    try:
        import psutil  # already a Sarthi dependency, optional for standalone use

        for proc in psutil.process_iter(["name", "memory_info"]):
            name = (proc.info.get("name") or "").lower()
            if "ollama" in name or "llama" in name:
                info = proc.info.get("memory_info")
                processes.append({"name": proc.info["name"], "rss_bytes": info.rss if info else None})
    except (ImportError, Exception) as exc:  # noqa: BLE001
        processes = [{"error": f"Process RSS unavailable: {exc}"}]
    return {"system": system, "ollama_processes": processes}


def loaded_models(base_url: str) -> list[dict[str, Any]]:
    """Snapshot Ollama's loaded model allocation from `/api/ps`."""
    try:
        with _request(base_url, "/api/ps", timeout=10) as response:
            return json.load(response).get("models", [])
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return []


def unload_model(base_url: str, model: str) -> bool:
    """Ask Ollama to unload a model before an explicitly cold request."""
    try:
        with _request(
            base_url,
            "/api/generate",
            {"model": model, "keep_alive": 0, "stream": False},
            timeout=60,
        ) as response:
            json.load(response)
        return True
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


def _stream_chat(base_url: str, model: str, prompt: dict, system: str, gen: dict, ctx: int):
    """Stream one fixed prompt and preserve Ollama's per-call counters."""
    messages = [{"role": "system", "content": system}]
    if prompt.get("instructions"):
        messages.append({"role": "system", "content": prompt["instructions"]})
    if prompt.get("memory"):
        messages.append({"role": "system", "content": "Memory:\n" + prompt["memory"]})
    for turn in prompt.get("history", []):
        if turn.get("role") in {"user", "assistant"} and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": prompt["prompt"]})
    request_payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "keep_alive": "5m",
        "options": {
            "num_ctx": ctx,
            "temperature": gen["temperature"],
            "seed": gen["seed"],
            "num_predict": gen["num_predict"],
        },
    }
    if prompt.get("structured"):
        # Match LocalHermesProvider's existing Ollama JSON mode when Hermes
        # requests structured output.
        request_payload["format"] = "json"
    started = time.perf_counter()
    first_token_at = None
    chunks: list[str] = []
    final: dict[str, Any] = {}
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=json.dumps(request_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=600) as response:
        for raw_line in response:
            if not raw_line.strip():
                continue
            item = json.loads(raw_line)
            token = (item.get("message") or {}).get("content", "")
            if token:
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                chunks.append(token)
            if item.get("done"):
                final = item
    ended = time.perf_counter()
    total_s = ended - started
    eval_count = final.get("eval_count")
    eval_duration = final.get("eval_duration")
    return {
        "text": "".join(chunks),
        "metrics": {
            "total_response_ms": total_s * 1000,
            "time_to_first_token_ms": (first_token_at - started) * 1000 if first_token_at else None,
            "generation_tokens_per_second": (
                eval_count / (eval_duration / 1e9) if eval_count and eval_duration else None
            ),
            "prompt_eval_tokens": final.get("prompt_eval_count"),
            "generation_tokens": eval_count,
            "load_duration_ms": final.get("load_duration", 0) / 1e6,
            "prompt_eval_duration_ms": final.get("prompt_eval_duration", 0) / 1e6,
            "generation_duration_ms": eval_duration / 1e6 if eval_duration else None,
            "total_duration_ms_reported": final.get("total_duration", 0) / 1e6,
        },
    }


def _model_map(inventory: dict) -> dict[str, dict]:
    return {row.get("name"): row for row in inventory.get("models", [])}


def run_benchmark(
    base_url: str,
    dataset: dict,
    inventory: dict,
    max_prompts: int | None,
    on_update=None,
    structured_only: bool = False,
):
    installed = _model_map(inventory)
    prompt_rows = dataset["prompts"][:max_prompts]
    if structured_only:
        prompt_rows = [prompt for prompt in prompt_rows if prompt.get("structured")]
    results: dict[str, Any] = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_script": str(Path(__file__).relative_to(ROOT)),
        "dataset": str(DATASET_PATH.relative_to(ROOT)),
        "dataset_version": dataset["dataset_version"],
        "ollama_url": base_url,
        "ollama_version": inventory.get("version"),
        "host": {"platform": platform.platform(), "python": sys.version.split()[0]},
        "context_sizes": list(CONTEXT_SIZES),
        "generation": dataset["generation"],
        "inventory": inventory,
        "candidates": [],
        "limitations": [
            "Quality checks are recorded as rubric prompts; outputs require human scoring.",
            "The first request per context follows an explicit model unload; later requests are warm. Unload success is recorded per context.",
            "RSS is sampled around requests and is process-level, so unrelated Ollama activity can affect it.",
        ],
    }
    for model in CANDIDATES:
        candidate: dict[str, Any] = {
            "model": model,
            "installed": model in installed,
            "metadata": installed.get(model),
            "status": "pending",
            "contexts": [],
        }
        if not inventory.get("reachable"):
            candidate["status"] = "skipped_ollama_unavailable"
            results["candidates"].append(candidate)
            continue
        if model not in installed:
            candidate["status"] = "skipped_not_installed"
            results["candidates"].append(candidate)
            continue
        candidate["status"] = "running"
        for ctx in CONTEXT_SIZES:
            cold_unload_succeeded = unload_model(base_url, model)
            context_row: dict[str, Any] = {
                "num_ctx": ctx,
                "cold_unload_succeeded": cold_unload_succeeded,
                "runs": [],
                "errors": [],
            }
            for index, prompt in enumerate(prompt_rows):
                memory_before = runtime_memory()
                ollama_loaded_before = loaded_models(base_url)
                try:
                    response = _stream_chat(
                        base_url, model, prompt, dataset["system_prompt"], dataset["generation"], ctx
                    )
                    memory_after = runtime_memory()
                    ollama_loaded_after = loaded_models(base_url)
                    metrics = response["metrics"]
                    metrics["request_class"] = "cold" if index == 0 else "warm"
                    metrics["cold_unload_succeeded"] = cold_unload_succeeded if index == 0 else None
                    if prompt.get("structured"):
                        try:
                            parsed = json.loads(response["text"])
                            metrics["structured_json_valid"] = isinstance(parsed, dict)
                            metrics["structured_tool_correct"] = (
                                parsed.get("tool") == prompt["expected_json"].get("tool")
                            )
                        except (json.JSONDecodeError, TypeError):
                            metrics["structured_json_valid"] = False
                            metrics["structured_tool_correct"] = False
                    metrics["memory_before"] = memory_before
                    metrics["memory_after"] = memory_after
                    metrics["ollama_loaded_before"] = ollama_loaded_before
                    metrics["ollama_loaded_after"] = ollama_loaded_after
                    context_row["runs"].append({
                        "prompt_id": prompt["id"],
                        "category": prompt["category"],
                        "response": response["text"],
                        "metrics": metrics,
                        "rubric": prompt.get("quality_checks", []),
                        "expected_emotion": prompt.get("expected_emotion"),
                        "expected_json": prompt.get("expected_json"),
                        "structured": bool(prompt.get("structured")),
                    })
                    print(f"{model} ctx={ctx}: {prompt['id']} complete", flush=True)
                    if on_update:
                        on_update(results)
                except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                    context_row["errors"].append({"prompt_id": prompt["id"], "error": str(exc)})
                    if index == 0:
                        candidate["status"] = "failed_request"
                        break
            candidate["contexts"].append(context_row)
            if candidate["status"] == "failed_request":
                break
        if candidate["status"] == "running":
            candidate["status"] = "completed"
        results["candidates"].append(candidate)
    return results


def render_report(results: dict) -> str:
    lines = [
        "# Hermes model benchmark — Phase 2A",
        "",
        f"Generated: {results.get('created_at', 'not run')}",
        f"Ollama: {results.get('ollama_version') or 'unavailable'} at `{results.get('ollama_url')}`",
        f"Dataset: `{results.get('dataset')}` (version {results.get('dataset_version')})",
        "",
        "## Verified runtime and inventory",
        "",
    ]
    inventory = results.get("inventory", {})
    lines.append(f"- Ollama API reachable: **{inventory.get('reachable', False)}**")
    lines.append(f"- Ollama executable on PATH: **{shutil.which('ollama') or 'not found'}**")
    config = inventory.get("production_config", {})
    lines.append(f"- Configured provider/model: `{config.get('provider')}` / `{config.get('model')}`")
    disk = inventory.get("disk", {})
    if disk.get("free_bytes"):
        lines.append(f"- Workspace disk free: {disk['free_bytes'] / 1e9:.1f} GB of {disk['total_bytes'] / 1e9:.1f} GB")
    if inventory.get("error"):
        lines.append(f"- API error: `{inventory['error']}`")
    lines += ["- Production settings were not changed.", "", "## Candidate status", ""]
    lines += ["| Candidate | Status | Installed size | Quantization |", "|---|---|---:|---|"]
    for candidate in results.get("candidates", []):
        meta = candidate.get("metadata") or {}
        details = meta.get("details", {})
        size = meta.get("size_bytes")
        size_text = f"{size / 1e9:.2f} GB" if size else "—"
        quant = meta.get("quantization") or details.get("quantization_level") or "—"
        lines.append(f"| `{candidate['model']}` | {candidate['status']} | {size_text} | {quant} |")
    completed = [c for c in results.get("candidates", []) if c.get("status") == "completed"]
    quality_reviews = {
        row["model"]: row for row in results.get("quality_review", {}).get("model_reviews", [])
    }
    lines += ["", "## Performance and quality comparison", ""]
    if not completed:
        lines.append("No candidate was benchmarked because the Ollama runtime was unavailable or the models were not installed. No quality or speed winner can be claimed from this run.")
    else:
        lines += [
            "| Model | Context | Requests | Cold TTFT ms | Warm TTFT ms | Warm tok/s | Mean response ms | Max loaded model GB | Tool JSON accuracy | Quality score |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
        for candidate in completed:
            for context in candidate["contexts"]:
                runs = context["runs"]
                cold_runs = [r for r in runs if r["metrics"].get("request_class") == "cold"]
                warm_runs = [r for r in runs if r["metrics"].get("request_class") == "warm"]
                structured_runs = [r for r in runs if r.get("structured")]

                def mean(rows, key):
                    values = [r["metrics"].get(key) for r in rows if r["metrics"].get(key) is not None]
                    return sum(values) / len(values) if values else None

                fmt = lambda v: f"{v:.1f}" if v is not None else "—"
                cold_ttft = mean(cold_runs, "time_to_first_token_ms")
                warm_ttft = mean(warm_runs, "time_to_first_token_ms")
                warm_tps = mean(warm_runs, "generation_tokens_per_second")
                response_ms = mean(runs, "total_response_ms")
                allocations = [
                    model.get("size")
                    for run in runs
                    for model in run["metrics"].get("ollama_loaded_after", [])
                    if model.get("name") == candidate["model"] and model.get("size") is not None
                ]
                max_gb = max(allocations) / 1e9 if allocations else None
                tool_correct = sum(
                    bool(r["metrics"].get("structured_tool_correct")) for r in structured_runs
                )
                tool_accuracy = (
                    f"{tool_correct}/{len(structured_runs)}" if structured_runs else "n/a"
                )
                quality = quality_reviews.get(candidate["model"], {}).get("overall_score")
                quality_text = f"{quality:.1f}/5" if quality is not None else "pending review"
                lines.append(
                    f"| `{candidate['model']}` | {context['num_ctx']} | {len(runs)} | {fmt(cold_ttft)} | "
                    f"{fmt(warm_ttft)} | {fmt(warm_tps)} | {fmt(response_ms)} | {fmt(max_gb)} | "
                    f"{tool_accuracy} | {quality_text} |"
                )
    review = results.get("quality_review")
    lines += ["", "## Qualitative quality review", ""]
    if review:
        lines += [
            review["review_method"],
            "",
            "| Model | Basic | Emotion | Personality | Memory | Tool choice | Overall | Review notes |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ]
        for row in review["model_reviews"]:
            scores = row["category_scores"]
            lines.append(
                f"| `{row['model']}` | {scores['basic_conversation']} | {scores['emotional_understanding']} | "
                f"{scores['personality_consistency']} | {scores['memory_recall']} | {scores['tool_selection']} | "
                f"{row['overall_score']:.1f}/5 | {row['notes']} |"
            )
    else:
        lines.append("Manual review pending.")
    lines += ["", "## Recommendation", ""]
    if review:
        lines += [review["recommendation"], "", review["context_recommendation"]]
    else:
        lines.append("**No model winner is selected yet.** Quality review is pending; keep the configured baseline and production settings unchanged.")
    lines += ["", "## Method and limitations", "", "- Candidates: `" + "`, `".join(CANDIDATES) + "`.",
        "- Context sizes: 2048, 4096, and 8192; temperature 0.2, seed 42, maximum 120 generated tokens.",
        "- Each prompt runs with the same dataset instructions and generation settings. The benchmark sets `num_ctx` per request.",
        "- Before each model/context cell, the harness asks Ollama to unload that model. The first request is labeled cold and following requests warm; unload success is recorded. Ollama `load_duration` is retained separately.",
        "- Memory snapshots include system memory, best-effort Ollama/runner RSS, and `/api/ps` loaded-model allocation before and after each request.",
        "- TTFT is measured from request start to the first non-empty streamed content. Token rate uses Ollama `eval_count / eval_duration`.",
        "- Outputs are saved unedited. Human reviewers should score each rubric item (pass/partial/fail) and structured JSON exact-key validity before selecting a winner.",
        "- The harness talks only to the local Ollama API for benchmark-only access to `num_ctx`, streaming timing, and runtime counters. It does not change the application's provider or tool-validation paths.",
        "- No downloads are initiated. Missing models are skipped.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("LOCAL_HERMES_URL", DEFAULT_URL))
    parser.add_argument("--inventory", action="store_true", help="inventory only; no model requests")
    parser.add_argument("--max-prompts", type=int, help="run only the first N prompts (smoke runs are not comparable)")
    parser.add_argument("--structured-only", action="store_true", help="rerun only structured prompts using Ollama JSON mode")
    parser.add_argument("--results", type=Path, default=RESULT_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    args = parser.parse_args()

    inventory = ollama_inventory(args.url)
    if args.inventory:
        print(json.dumps(inventory, indent=2))
        return 0 if inventory["reachable"] else 2
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    progress_results = (
        args.results.with_name(args.results.stem + "_structured_partial.json")
        if args.structured_only
        else args.results
    )
    progress_report = (
        args.report.with_name(args.report.stem + "_structured_partial.md")
        if args.structured_only
        else args.report
    )

    def save_progress(current):
        progress_results.parent.mkdir(parents=True, exist_ok=True)
        progress_results.write_text(
            json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        progress_report.write_text(render_report(current), encoding="utf-8")

    results = run_benchmark(
        args.url, dataset, inventory, args.max_prompts, save_progress, args.structured_only
    )
    if args.structured_only and args.results.is_file():
        prior = json.loads(args.results.read_text(encoding="utf-8"))
        prior_by_model = {row["model"]: row for row in prior.get("candidates", [])}
        new_by_model = {row["model"]: row for row in results.get("candidates", [])}
        for model, new_candidate in new_by_model.items():
            old_candidate = prior_by_model.get(model)
            if not old_candidate:
                continue
            for new_context in new_candidate["contexts"]:
                old_context = next(
                    (row for row in old_candidate["contexts"] if row["num_ctx"] == new_context["num_ctx"]),
                    None,
                )
                if not old_context:
                    old_candidate["contexts"].append(new_context)
                    continue
                replacements = {row["prompt_id"]: row for row in new_context["runs"]}
                old_context["runs"] = [
                    replacements.pop(row["prompt_id"], row) for row in old_context["runs"]
                ] + list(replacements.values())
                old_context["cold_unload_succeeded"] = new_context["cold_unload_succeeded"]
                old_context["errors"].extend(new_context["errors"])
            old_candidate["status"] = new_candidate["status"]
        results = prior
        results["structured_json_mode_rerun_at"] = datetime.now(timezone.utc).isoformat()
        results["limitations"].append(
            "Structured prompts were rerun in Ollama JSON mode to match the existing production provider's structured-output behavior; those structured rows replace the initial free-form run."
        )
    quality_path = ROOT / "docs" / "dev" / "hermes_model_benchmark_quality_review.json"
    if quality_path.is_file():
        results["quality_review"] = json.loads(quality_path.read_text(encoding="utf-8"))
    args.results.parent.mkdir(parents=True, exist_ok=True)
    args.results.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.report.write_text(render_report(results), encoding="utf-8")
    if args.structured_only:
        progress_results.unlink(missing_ok=True)
        progress_report.unlink(missing_ok=True)
    print(f"Results: {args.results}")
    print(f"Report:  {args.report}")
    print("No models were downloaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
