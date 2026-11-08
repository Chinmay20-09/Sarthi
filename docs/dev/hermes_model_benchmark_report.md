# Hermes model benchmark — Phase 2A

Generated: 2026-11-06T11:06:10.358604+00:00
Ollama: 0.40.13 at `http://localhost:11434`
Dataset: `docs\dev\hermes_model_benchmark_prompts.json` (version 1)

## Verified runtime and inventory

- Ollama API reachable: **True**
- Ollama executable on PATH: **C:\Users\Chinmay kolte\AppData\Local\Programs\Ollama\ollama.EXE**
- Configured provider/model: `local` / `hermes3:8b`
- Workspace disk free: 123.3 GB of 510.5 GB
- Production settings were not changed.

## Candidate status

| Candidate | Status | Installed size | Quantization |
| --- | --- | ---: | --- |
| `hermes3:8b` | completed | 4.66 GB | Q4_0 |
| `hermes3:8b-llama3.1-q3_K_M` | completed | 4.02 GB | Q3_K_M |
| `hermes3:3b` | completed | 2.02 GB | Q4_K_M |
| `hermes3:3b-llama3.2-q3_K_M` | completed | 1.69 GB | Q3_K_M |

## Performance and quality comparison

| Model | Context | Requests | Cold TTFT ms | Warm TTFT ms | Warm tok/s | Mean response ms | Max loaded model GB | Tool JSON accuracy | Quality score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `hermes3:8b` | 2048 | 22 | 14641.4 | 2883.2 | 7.2 | 8015.7 | 5.1 | 3/3 | 4.6/5 |
| `hermes3:8b` | 4096 | 22 | 13800.5 | 2946.5 | 6.9 | 8316.6 | 5.3 | 3/3 | 4.6/5 |
| `hermes3:8b` | 8192 | 22 | 14121.5 | 2928.0 | 6.9 | 8291.0 | 6.0 | 3/3 | 4.6/5 |
| `hermes3:8b-llama3.1-q3_K_M` | 2048 | 22 | 18331.3 | 2941.6 | 7.3 | 9316.8 | 4.4 | 2/3 | 4.2/5 |
| `hermes3:8b-llama3.1-q3_K_M` | 4096 | 22 | 12093.3 | 2919.4 | 7.8 | 8259.0 | 4.7 | 2/3 | 4.2/5 |
| `hermes3:8b-llama3.1-q3_K_M` | 8192 | 22 | 9637.6 | 2915.7 | 7.8 | 8063.4 | 5.4 | 2/3 | 4.2/5 |
| `hermes3:3b` | 2048 | 22 | 9635.4 | 2408.1 | 13.0 | 8126.3 | 2.3 | 2/3 | 3.2/5 |
| `hermes3:3b` | 4096 | 22 | 7465.4 | 2402.7 | 13.3 | 7749.2 | 2.6 | 2/3 | 3.2/5 |
| `hermes3:3b` | 8192 | 22 | 7377.3 | 2404.5 | 13.1 | 7777.7 | 3.1 | 2/3 | 3.2/5 |
| `hermes3:3b-llama3.2-q3_K_M` | 2048 | 22 | 6723.0 | 2423.7 | 14.6 | 7889.1 | 2.0 | 1/3 | 2.0/5 |
| `hermes3:3b-llama3.2-q3_K_M` | 4096 | 22 | 6322.3 | 2420.0 | 14.7 | 7776.1 | 2.2 | 1/3 | 2.0/5 |
| `hermes3:3b-llama3.2-q3_K_M` | 8192 | 22 | 6419.3 | 2415.0 | 14.9 | 7826.8 | 2.8 | 1/3 | 2.0/5 |

## Qualitative quality review

Human qualitative review of the 2048-context responses against the fixed dataset checks. Scores are judgment calls, not automated model metrics; structured tool accuracy is measured separately in the benchmark results.

| Model | Basic | Emotion | Personality | Memory | Tool choice | Overall | Review notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `hermes3:8b` | 5 | 4 | 4 | 5 | 5 | 4.6/5 | Most natural and concise overall; identifies emotional tone and follows memory. Tool choices are correct in all three structured cases. A few responses are generic or too enthusiastic. |
| `hermes3:8b-llama3.1-q3_K_M` | 5 | 4 | 4 | 5 | 3 | 4.2/5 | Conversational and emotionally aware, with concise memory recall. Under Ollama JSON mode it returns an empty object for the no-tool arithmetic case, so structured choice is not reliable enough. |
| `hermes3:3b` | 3 | 3 | 2 | 5 | 3 | 3.2/5 | Memory recall and some simple responses are good, but answers are often long, the tired-user request is ignored, and it selects search_web for a simple multiplication question. |
| `hermes3:3b-llama3.2-q3_K_M` | 2 | 1 | 1 | 5 | 1 | 2.0/5 | Memory recall is correct, but several unrelated JSON/tool-shaped responses appear in plain conversation. It gives off-topic emotional answers, emits malformed structured output, and selects a tool for simple arithmetic. |

## Recommendation

Keep hermes3:8b as the current production model. At 2048 context it is the only candidate with 3/3 correct structured tool choices and consistently acceptable conversational behavior. The 3B models substantially reduce memory and improve warm token speed, but their tool-selection errors and quality misses fail this workload's minimum reliability bar. The 8B Q3 candidate is not a good compromise: it is only modestly smaller/faster than baseline and missed one of three structured choices. Do not change production defaults without explicit review and approval.

For a future controlled trial, 2048 context is the best starting point: the baseline's loaded-model allocation was about 5.05 GB versus 6.0 GB at 8192, with slightly higher measured warm throughput. This does not alter the production context setting.

## Method and limitations

- Candidates: `hermes3:8b`, `hermes3:8b-llama3.1-q3_K_M`, `hermes3:3b`, `hermes3:3b-llama3.2-q3_K_M`.
- Context sizes: 2048, 4096, and 8192; temperature 0.2, seed 42, maximum 120 generated tokens.
- Each prompt runs with the same dataset instructions and generation settings. The benchmark sets `num_ctx` per request.
- Before each model/context cell, the harness asks Ollama to unload that model. The first request is labeled cold and following requests warm; unload success is recorded. Ollama `load_duration` is retained separately.
- Memory snapshots include system memory, best-effort Ollama/runner RSS, and `/api/ps` loaded-model allocation before and after each request.
- TTFT is measured from request start to the first non-empty streamed content. Token rate uses Ollama `eval_count / eval_duration`.
- Outputs are saved unedited. Human reviewers should score each rubric item (pass/partial/fail) and structured JSON exact-key validity before selecting a winner.
- The harness talks only to the local Ollama API for benchmark-only access to `num_ctx`, streaming timing, and runtime counters. It does not change the application's provider or tool-validation paths.
- No downloads are initiated. Missing models are skipped.
