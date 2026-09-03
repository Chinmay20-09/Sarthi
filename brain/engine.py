"""
Brain Engine — main orchestrator for Sarthi's brain pipeline.

The BrainEngine wires together the full pipeline:
    Interpreter → Planner → Resolver → Executor

It is the SINGLE public entry point for the brain package.
All command processing goes through BrainEngine.process().

Skills are auto-loaded on startup and registered with the executor.

Usage:
    from brain.engine import BrainEngine

    engine = BrainEngine()
    response = engine.process("open Chrome")
    print(response.status)  # "executed"
"""

import logging
from datetime import datetime
from typing import Any

from brain.context import BrainContext
from brain.executor import BrainExecutor
from brain.intent import Intent
from brain.interpreter import interpret_many
from brain.planner import Planner
from brain.response import BrainResponse, step_payload
from knowledge.entity_resolver import EntityResolver

logger = logging.getLogger(__name__)


class BrainEngine:
    """
    Orchestrates the full brain pipeline.

    Wires together:
        - Interpreter (parses text → Intent)
        - Planner (decomposes compound commands → List[Intent])
        - Resolver (resolves entity names via fuzzy matching)
        - Executor (dispatches to handlers, including skills)

    Automatically loads and registers all installed skills on startup.

    Accepts entities via dependency injection. If none provided,
    lazily loads from KnowledgeManager.

    Usage:
        engine = BrainEngine()
        response = engine.process("open Chrome")
        print(response.to_api_dict())
    """

    def __init__(
        self,
        resolver: EntityResolver | None = None,
        executor: BrainExecutor | None = None,
        planner: Planner | None = None,
    ):
        """
        Initialize the Brain Engine.

        Args:
            resolver: EntityResolver instance. If None, loads from KnowledgeManager.
            executor: BrainExecutor instance. If None, creates default.
            planner: Planner instance. If None, creates default pass-through planner.
        """
        self.planner = planner or Planner()
        self.executor = executor or BrainExecutor()

        if resolver:
            self.resolver = resolver
        else:
            # Lazily load entities from KnowledgeManager
            logger.info("No resolver provided — loading entities from KnowledgeManager")
            try:
                from knowledge.manager import get_manager as get_knowledge_manager

                manager = get_knowledge_manager()
                entities = manager.get_all_entities()
                self.resolver = EntityResolver(entities=entities)
                logger.info(f"Loaded {len(entities)} entities into resolver")
            except Exception as e:
                logger.warning(f"Could not load entities: {e}")
                self.resolver = EntityResolver()

        # Auto-load and register skills via SkillRegistry
        self._load_skills()

    # ------------------------------------------------------------------
    # Skill loading via Registry
    # ------------------------------------------------------------------

    def _load_skills(self) -> None:
        """Discover, instantiate, and register all installed skills via SkillRegistry."""
        try:
            from skills.registry import get_registry

            registry = get_registry()
            skills = registry.get_all_instances()
            # Fallback skills (e.g. Natural Language Processor) are tried LAST:
            # every real tool/skill gets a chance to handle the intent first.
            skills.sort(key=lambda s: getattr(s, "fallback", False))
            for skill in skills:
                self.executor.register_skill(skill)
                logger.info(f"Registered skill: {skill.name} v{skill.version}")
        except Exception as e:
            logger.warning(f"Could not load skills: {e}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, text: str) -> BrainResponse:
        """
        Process a natural language command through the full pipeline.

        Pipeline:
            1. Interpret text → List[Intent] (one per '.'-separated query,
               "open X and search/play Y" expands to two intents)
            2. Plan → List[Intent] (multi-step support)
            3. Resolve entities → enriched Intent
            4. Execute → result

        Args:
            text: Raw natural language input (e.g., "open Chrome")

        Returns:
            BrainResponse with status, result, and timing info
        """
        start = datetime.now()
        context = BrainContext(original_text=text)

        try:
            # Step 1: Interpret — every '.'-separated query becomes an intent,
            # and "open X and search/play Y" becomes an open + a search/play
            # intent, so multi-query input executes each part in sequence.
            context.stage = "interpret"
            intents = interpret_many(text)
            # interpret_many returns [] only for empty/all-punctuation input;
            # fall back to an unknown intent so the pipeline still completes.
            if not intents:
                from brain.intent import Intent

                intents = [Intent(action="unknown", raw_text=text or "")]
            context.intent = intents[0]
            logger.debug(
                f"Interpreted {len(intents)} intent(s): {intents[0].action} {intents[0].target}"
            )

            # Step 2: Plan — each parsed intent flows through the planner
            context.stage = "plan"
            plan: list[Intent] = []
            for intent in intents:
                plan.extend(self.planner.plan(intent, context))

            # Step 3: Resolve
            context.stage = "resolve"
            resolved = self._resolve_plan(plan, context)

            # Step 4: Execute
            context.stage = "execute"
            result, steps = self._execute_plan(resolved, context)

            elapsed = (datetime.now() - start).total_seconds() * 1000

            return BrainResponse(
                intent=context.intent,
                success=result.get("success", False),
                status=result.get("status", "completed"),
                action_result=result.get("result"),
                execution_ms=elapsed,
                error=result.get("error"),
                resolved=context.resolved,
                steps=steps or None,
            )

        except Exception as e:
            elapsed = (datetime.now() - start).total_seconds() * 1000
            logger.error(f"Pipeline error: {e}", exc_info=True)

            return BrainResponse(
                intent=context.intent,
                success=False,
                status="error",
                error=str(e),
                execution_ms=elapsed,
            )

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    def _resolve_plan(self, plan: list[Intent], context: BrainContext) -> list[Intent]:
        """Resolve entities for all intents in the plan."""
        resolved = []
        resolved_any = False
        for intent in plan:
            if intent.target:
                resolved_target = self.resolver.resolve(intent.target)
                if resolved_target != intent.target:
                    resolved_any = True
                    logger.debug(f"Resolved '{intent.target}' -> '{resolved_target}'")
                intent.target = resolved_target
            resolved.append(intent)

        # Update context with the (last) resolved intent
        if resolved:
            context.intent = resolved[-1]

        # Tell downstream consumers whether resolution actually happened
        context.resolved = resolved_any
        return resolved

    def _execute_plan(
        self, plan: list[Intent], context: BrainContext
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Execute all intents in the plan sequentially.

        Returns the last (or failing) result plus an API-shaped payload for
        EVERY executed step, so multi-query commands can show one card per
        action instead of only the final reply.
        """
        final_result: dict[str, Any] = {"success": True, "status": "completed"}
        steps: list[dict[str, Any]] = []

        for step_idx, intent in enumerate(plan):
            logger.debug(f"Executing step {step_idx + 1}/{len(plan)}")
            result = self.executor.execute(intent, context)
            steps.append(step_payload(intent, result))

            if not result.get("success", False):
                # Fail fast — stop on first error (the failing step is kept
                # in ``steps`` so the UI can show where it stopped)
                return result, steps

            final_result = result

        return final_result, steps
