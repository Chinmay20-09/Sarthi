"""
ai_chain/chain.py

Orchestrates a two-AI chain over the laptop:

    query ──▶ AI1 (ChatGPT) ──response──▶ prompt for AI2 (Gemini) ──▶ save

Before it moves the mouse it prints a HANDS-OFF warning with a countdown
and tells the user exactly how to abort (Ctrl+Alt+X, or slam the mouse
into a screen corner — PyAutoGUI failsafe). Every step's prompt and
response are saved to the run folder, and when AI2 is image-capable the
generated image is downloaded too.

Supports ``dry_run``: builds the plan and reports it without touching
the machine (used by unit tests and Sarthi test mode).
"""

from __future__ import annotations

import time
from pathlib import Path

from brain.modes import get_test_mode
from utils.logger import get_logger
from utils.voice import announce

from . import handoff
from .calibration import get_downloads_dir, resolve_site
from .control import AbortError, ScreenController
from .dom import reset_dom_reader
from .models import ChainOutcome, ChainRequest, SiteSpec, StepOutcome
from .sites import WebAiDriver
from .storage import ChainRun

logger = get_logger(__name__)

HANDS_OFF_MESSAGE = """
====================================================================
 ⚠  AI CHAIN — HANDS-OFF MODE
 -------------------------------------------------------------------
 Sarthi is about to take control of your keyboard and mouse to drive
 the AI sites for you (in its own automation Chrome window).

 ▶ DO NOT touch your keyboard or mouse while it works.
 ▶ First run only: log in to each site once in the automation window;
   the session is remembered for later runs.
 ▶ To abort at any moment:
      • press  Ctrl+Alt+X
      • or slam the mouse into any screen corner (failsafe)
====================================================================
"""

COUNTDOWN_SECONDS = 5

# Spoken announcements (docs/ABSOLUTE.md — system-handled automation).
VOICE_HANDS_OFF = (
    "Hands off. Automation started. "
    "Please step away from the keyboard and mouse while Sarthi is working."
)
VOICE_DONE = "Automation finished. You can use your computer now."
VOICE_CANCELLED = "Automation cancelled. You can use your computer now."


def run_ai_chain(
    query: str,
    ai1: str = "chatgpt",
    ai2: str = "gemini",
    save_images: bool = True,
    execute: bool | None = None,
    controller: ScreenController | None = None,
    results_root: Path | None = None,
) -> ChainOutcome:
    """
    Run (or plan) the chain ``query -> AI1 -> AI2``.

    Args:
        query: The user's request, sent verbatim to AI1.
        ai1 / ai2: Site keys or aliases ("chatgpt", "gemini", ...).
        save_images: Also download an image when AI2 produced one.
        execute: False forces a dry-run plan; True forces real control;
                 None defers to Sarthi test mode.
        controller: Inject a ScreenController (tests / headless usage).
        results_root: Where run folders are created (default results/ai_chain).

    Returns:
        ChainOutcome describing every step, saved files, and status.
    """
    request = ChainRequest(query=query, ai1=ai1, ai2=ai2, save_images=save_images)
    if execute is None:
        execute = not get_test_mode()

    try:
        spec1, spec2 = resolve_site(request.ai1), resolve_site(request.ai2)
    except ValueError as exc:
        outcome = ChainOutcome(request=request, success=False, status="failed", message=str(exc))
        if execute:
            _save_to_sandbox(request, outcome)
        return outcome

    if not execute:
        return _plan_only(request, spec1, spec2)

    print(HANDS_OFF_MESSAGE)
    logger.warning("AI chain starting — HANDS OFF the keyboard and mouse.")
    announce(VOICE_HANDS_OFF)

    ctrl = controller or ScreenController(dry_run=False)
    try:
        _countdown(ctrl)
    except AbortError as exc:
        ctrl.release()
        announce(VOICE_CANCELLED)
        print("Hands-off mode ended — you can use your keyboard and mouse again.")
        outcome = ChainOutcome(
            request=request, success=False, status="aborted", message=f"Aborted: {exc}"
        )
        _save_to_sandbox(request, outcome)
        return outcome

    run = ChainRun(request.query, root=results_root)
    run.write_text("01_query.txt", request.query)
    handoff.reset()  # the backend starts clean with every run
    steps: list[StepOutcome] = []

    try:
        # Step 1 — send the user's query to AI1.
        step1 = _drive(ctrl, run, spec1, request.query, index=1)
        steps.append(step1)
        if not step1.success:
            return _finish_and_record(
                request,
                steps,
                run,
                "failed",
                f"AI1 ({spec1.label}) failed: {step1.error}",
            )

        # Step 2 — send AI1's reply to AI2 as the prompt. The prompt is
        # sourced FROM the backend hand-off (the saved copy), not from the
        # clipboard or the in-memory step result — the clipboard is scratch
        # space the verification copies keep overwriting.
        backend_prompt = handoff.load("step1_response") or step1.response
        step2 = _drive(ctrl, run, spec2, backend_prompt, index=2)
        steps.append(step2)
        if not step2.success:
            return _finish_and_record(
                request,
                steps,
                run,
                "failed",
                f"AI2 ({spec2.label}) failed: {step2.error}",
            )

        harvested = []
        if request.save_images and spec2.image_capable:
            found = WebAiDriver(ctrl).download_last_image(spec2, get_downloads_dir())
            if found is not None:
                kept = run.harvest_file(found)
                step2.artifacts.append(kept)
                harvested.append(str(kept))

        message = f"Chain completed: {spec1.label} -> {spec2.label}. Run folder: {run.dir}"
        if harvested:
            message += f" | image: {harvested[0]}"
        return _finish_and_record(request, steps, run, "completed", message)

    except AbortError as exc:
        return _finish_and_record(request, steps, run, "aborted", f"Aborted: {exc}")
    except Exception as exc:
        logger.exception("AI chain failed")
        return _finish_and_record(request, steps, run, "failed", f"Chain failed: {exc}")
    finally:
        ctrl.release()
        # Drop the v1.5 CDP attachment (if any) so the browser session is
        # released and the next run re-checks for a debug port.
        reset_dom_reader()
        announce(VOICE_DONE)
        print("Hands-off mode ended — you can use your keyboard and mouse again.")


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------


def _drive(
    ctrl: ScreenController,
    run: ChainRun,
    spec: SiteSpec,
    prompt: str,
    index: int,
) -> StepOutcome:
    """Drive one AI site: send the prompt, capture and save the reply."""
    started = time.perf_counter()
    outcome = StepOutcome(index=index, site_key=spec.key, site_label=spec.label, prompt=prompt)
    handoff.save(f"step{index}_prompt", prompt)  # backend copy for paste retries
    try:
        response = WebAiDriver(ctrl).ask(spec, prompt, prompt_key=f"step{index}_prompt")
        outcome.response = response
        if response.strip():
            artifact = run.write_text(f"0{index}_step{index}_{spec.key}_response.txt", response)
            outcome.artifacts.append(artifact)
            handoff.save(f"step{index}_response", response)
        else:
            outcome.error = "AI returned an empty reply"
    except AbortError as exc:
        outcome.error = str(exc)
        raise
    except Exception as exc:
        outcome.error = str(exc)
    finally:
        outcome.duration_ms = int((time.perf_counter() - started) * 1000)
    return outcome


def _countdown(ctrl: ScreenController) -> None:
    """Give the user time to get their hands away from the machine."""
    for remaining in range(COUNTDOWN_SECONDS, 0, -1):
        ctrl.check_abort()
        print(f"  Starting in {remaining}s ...  (Ctrl+Alt+X or mouse corner to abort)")
        time.sleep(1)
    ctrl.check_abort()


def _plan_only(request: ChainRequest, spec1: SiteSpec, spec2: SiteSpec) -> ChainOutcome:
    """Dry-run: describe exactly what a real run would do, touch nothing."""
    steps = [
        StepOutcome(index=1, site_key=spec1.key, site_label=spec1.label, prompt=request.query),
        StepOutcome(
            index=2,
            site_key=spec2.key,
            site_label=spec2.label,
            prompt=f"<reply from {spec1.label}>",
        ),
    ]
    plan = [
        f'1. Open {spec1.label} and send: "{request.query}"',
        f"2. Open {spec2.label} and paste AI1's reply as the prompt",
        "3. Save every response to the run folder",
    ]
    if request.save_images and spec2.image_capable:
        plan.append(f"4. Download the image {spec2.label} generates (if any)")
    message = "Planned chain: " + " | ".join(plan)
    logger.info(message)
    return ChainOutcome(
        request=request,
        success=True,
        status="planned",
        steps=steps,
        message=message,
    )


def _finish(
    request: ChainRequest,
    steps: list[StepOutcome],
    run: ChainRun,
    status: str,
    message: str,
) -> ChainOutcome:
    return ChainOutcome(
        request=request,
        success=status == "completed",
        status=status,
        steps=steps,
        run_dir=run.dir,
        message=message,
    )


def _finish_and_record(
    request: ChainRequest,
    steps: list[StepOutcome],
    run: ChainRun,
    status: str,
    message: str,
) -> ChainOutcome:
    """Build the outcome and record it in the Hermes sandbox (real runs)."""
    outcome = _finish(request, steps, run, status, message)
    _save_to_sandbox(request, outcome)
    return outcome


def _save_to_sandbox(request: ChainRequest, outcome: ChainOutcome) -> None:
    """
    Record a real chain run in the Hermes sandbox so failed/aborted queries
    stay visible in the sandbox viewer (and are kept by /clean).

    Dry-run plans are never recorded. A sandbox failure must never change
    the chain outcome, so everything is wrapped and only logged.
    """
    try:
        from hermes.config.loader import ConfigLoader
        from hermes.models import Task
        from hermes.providers.base import ProviderResponse
        from hermes.sandbox import TaskSandbox

        trace = [
            {
                "site": step.site_key,
                "prompt": step.prompt,
                "response": step.response,
                "error": step.error,
                "duration_ms": step.duration_ms,
            }
            for step in outcome.steps
        ]

        text = outcome.message or ""
        if outcome.run_dir is not None:
            text = f"{text}\nRun folder: {outcome.run_dir}"

        response = ProviderResponse(
            success=outcome.success,
            provider="ai_chain",
            model=f"{request.ai1} -> {request.ai2}",
            text=text,
            error="" if outcome.success else (outcome.message or "ai_chain failed"),
            tool_used="ai_chain",
        )
        task = Task(prompt=request.query, task_type="ai_chain")

        sandbox = TaskSandbox(ConfigLoader().load().sandbox_path)
        sandbox.save(
            task,
            response,
            duration_ms=sum(step.duration_ms for step in outcome.steps),
            trace=trace,
        )
        logger.info(f"ai_chain run recorded in sandbox: {request.query!r} ({outcome.status})")
    except Exception:
        logger.exception("Could not save ai_chain run to sandbox")
