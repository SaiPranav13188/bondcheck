"""Run context: streams agent events to the UI and logs every agent's steps to `agent_runs`."""
from __future__ import annotations

import logging
import queue
import time
import uuid
from contextlib import contextmanager
from typing import Any

from core.llm import TokenMeter

log = logging.getLogger("bondcheck.run")

_CONTEXTS: dict[str, "RunContext"] = {}


class RunContext:
    def __init__(self, workflow: str, run_ref: str | None = None, persist: bool = True):
        self.run_ref = run_ref or uuid.uuid4().hex[:12]
        self.workflow = workflow
        self.meter = TokenMeter()
        self.events: queue.Queue = queue.Queue()
        self.persist = persist
        self.agent_stack: list[AgentRun] = []
        self.started = time.monotonic()
        self.orchestrator_steps: list[dict] = []
        self.result: dict | None = None

    def emit(self, agent: str, kind: str, message: str, **data: Any) -> None:
        """kind: start | tool | check | decision | retry | ask | done | error | info"""
        ev = {"agent": agent, "kind": kind, "message": message, "t": round(time.monotonic() - self.started, 3),
              **({"data": data} if data else {})}
        if agent == "Orchestrator":
            self.orchestrator_steps.append(ev)
        elif self.agent_stack:
            self.agent_stack[-1].steps.append(ev)
        self.events.put(ev)

    def log_orchestrator(self, status: str) -> None:
        """Write the Orchestrator's own plan/routing/retry steps as one agent_runs row."""
        if not self.persist or not self.orchestrator_steps:
            return
        from tools.database import log_agent_run

        try:
            log_agent_run(run_ref=self.run_ref, workflow=self.workflow, agent="Orchestrator",
                          steps=self.orchestrator_steps, tokens=self.meter.used,
                          duration_ms=int((time.monotonic() - self.started) * 1000), status=status)
        except Exception:
            log.exception("could not write orchestrator agent_runs row")
        self.orchestrator_steps = []

    @contextmanager
    def agent(self, name: str):
        run = AgentRun(self, name)
        self.agent_stack.append(run)
        self.emit(name, "start", f"{name} started")
        try:
            yield run
        except Exception as e:
            run.status = "failed" if run.status == "success" else run.status
            self.emit(name, "error", f"{name} failed: {e}")
            raise
        finally:
            self.agent_stack.pop()
            run.finish()


class AgentRun:
    def __init__(self, ctx: RunContext, name: str):
        self.ctx = ctx
        self.name = name
        self.steps: list[dict] = []
        self.status = "success"
        self.tokens_start = ctx.meter.used
        self.t0 = time.monotonic()

    def finish(self) -> None:
        if not self.ctx.persist:
            return
        from tools.database import log_agent_run

        try:
            log_agent_run(run_ref=self.ctx.run_ref, workflow=self.ctx.workflow, agent=self.name, steps=self.steps,
                          tokens=self.ctx.meter.used - self.tokens_start,
                          duration_ms=int((time.monotonic() - self.t0) * 1000), status=self.status)
        except Exception:  # logging must never break a run
            log.exception("could not write agent_runs row")


def register(ctx: RunContext) -> RunContext:
    _CONTEXTS[ctx.run_ref] = ctx
    return ctx


def get(run_ref: str) -> RunContext:
    return _CONTEXTS[run_ref]


def drop(run_ref: str) -> None:
    _CONTEXTS.pop(run_ref, None)
