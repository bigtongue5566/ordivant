"""Rerunnable P0/P1 Work and shared-collaboration acceptance for local QA only."""

from __future__ import annotations

import argparse
import base64
import csv
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
QA_BASE_URL = "http://127.0.0.1:8096"
QA_COMPOSE_PROJECT = "ordivant-collaboration-qa-20261014"
SOURCE_CONTEXT = ROOT / ".cache" / "collaboration-qa" / "context.json"
OUTPUT_DIR = ROOT / ".cache" / "p0-p1-qa"


class AcceptanceError(RuntimeError):
    pass


class PlanningAcceptance:
    def __init__(self, base_url: str, compose_project: str):
        self.base_url = base_url.rstrip("/")
        self.compose_project = compose_project
        self.run_id = uuid.uuid4().hex[:10]
        self.prefix = f"P0P1-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{self.run_id}"
        self.clients: dict[str, httpx.Client] = {}
        self.principals: dict[str, str] = {}
        self.checks: dict[str, bool] = {}
        self.resources: dict[str, Any] = {}

    def check(self, name: str, condition: bool) -> None:
        self.checks[name] = bool(condition)
        if not condition:
            raise AcceptanceError(f"{name} failed")

    def validate_target(self) -> None:
        parsed = urlsplit(self.base_url)
        if (
            self.base_url != QA_BASE_URL
            or parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.port != 8096
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise AcceptanceError("Only http://127.0.0.1:8096 is allowed")
        if self.compose_project != QA_COMPOSE_PROJECT:
            raise AcceptanceError("Only the dedicated P0/P1 QA Compose project is allowed")

    def verify_compose_scope(self) -> None:
        try:
            result = subprocess.run(
                [
                    "docker", "compose", "--project-name", QA_COMPOSE_PROJECT,
                    "--file", str(ROOT / "compose.yaml"), "ps", "--services", "--status", "running",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=25,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise AcceptanceError("Could not verify the dedicated QA Compose project") from None
        services = set(result.stdout.splitlines()) if result.returncode == 0 else set()
        required = {"web", "work-api", "identity-api", "knowledge-api"}
        if not required.issubset(services):
            raise AcceptanceError("The dedicated QA Compose services are not all running")
        self.check("compose_scope_is_exact_qa_project", True)
        self.check("compose_core_services_running", True)

    def load_context(self) -> dict[str, Any]:
        try:
            context = json.loads(SOURCE_CONTEXT.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise AcceptanceError("Could not read the saved synthetic QA context") from None
        if not isinstance(context, dict) or context.get("base_url") != QA_BASE_URL:
            raise AcceptanceError("Saved synthetic QA context belongs to another host")
        work = context.get("work")
        users = context.get("users")
        knowledge = context.get("knowledge")
        if not isinstance(work, dict) or not isinstance(users, dict) or not isinstance(knowledge, dict):
            raise AcceptanceError("Saved synthetic QA context is incomplete")
        project_id = work.get("project_id")
        space_id = knowledge.get("space_id")
        if not isinstance(project_id, str) or not isinstance(space_id, str):
            raise AcceptanceError("Saved synthetic QA scope IDs are missing")
        self.resources.update(project_id=project_id, knowledge_space_id=space_id)
        identity_run_id = context.get("run_id")
        if not isinstance(identity_run_id, str) or not identity_run_id:
            raise AcceptanceError("Saved synthetic QA Identity run ID is missing")
        self.resources["identity_run_id"] = identity_run_id
        raw_resources = ((context.get("_qa_state") or {}).get("resources") or {})
        isolated = raw_resources.get("work_isolated_project") if isinstance(raw_resources, dict) else None
        if isinstance(isolated, dict):
            isolated = isolated.get("id")
        if isinstance(isolated, str):
            self.resources["isolated_project_id"] = isolated

        for name in ("admin", "alice", "bob", "reader"):
            entry = users.get(name)
            if not isinstance(entry, dict):
                raise AcceptanceError(f"Saved synthetic {name} session is missing")
            cookie_name = entry.get("cookie_name")
            cookie_value = entry.get("cookie_value")
            csrf_token = entry.get("csrf_token")
            if not all(isinstance(value, str) and value for value in (cookie_name, cookie_value, csrf_token)):
                raise AcceptanceError(f"Saved synthetic {name} session is incomplete")
            client = httpx.Client(
                base_url=QA_BASE_URL,
                headers={"Origin": QA_BASE_URL, "X-CSRF-Token": csrf_token},
                timeout=httpx.Timeout(25, connect=5),
                follow_redirects=False,
                trust_env=False,
            )
            client.cookies.set(cookie_name, cookie_value)
            self.clients[name] = client
            saved_principal = entry.get("principal_id")
            if isinstance(saved_principal, str) and saved_principal:
                self.principals[name] = saved_principal
        return context

    def request(
        self,
        actor: str,
        method: str,
        path: str,
        *,
        body: Any = None,
        params: dict[str, str] | None = None,
        expected: int = 200,
        label: str,
        product_prefix: str = "",
    ) -> httpx.Response:
        client = self.clients[actor]
        headers: dict[str, str] = {}
        if method.upper() not in {"GET", "HEAD"}:
            slug = re.sub(r"[^a-z0-9]+", "-", label.casefold()).strip("-")[:70]
            headers["Idempotency-Key"] = f"qa-p0p1-{self.run_id}-{slug}"
        try:
            response = client.request(method, f"{product_prefix}{path}", json=body, params=params, headers=headers)
        except httpx.HTTPError:
            raise AcceptanceError(f"{label}: request failed") from None
        if response.status_code != expected:
            validation = ""
            if response.status_code == 422:
                try:
                    details = response.json().get("detail", [])
                    if isinstance(details, list):
                        fields = [
                            f"{'.'.join(str(part) for part in item.get('loc', []))}: {str(item.get('msg', ''))[:120]}"
                            for item in details[:5] if isinstance(item, dict)
                        ]
                        validation = f" ({'; '.join(fields)})" if fields else ""
                except (ValueError, AttributeError, TypeError):
                    pass
            raise AcceptanceError(f"{label}: HTTP {response.status_code}, expected {expected}{validation}")
        return response

    def json(self, actor: str, method: str, path: str, **kwargs: Any) -> Any:
        response = self.request(actor, method, path, **kwargs)
        try:
            return response.json()
        except ValueError:
            raise AcceptanceError(f"{kwargs.get('label', 'API request')}: API returned invalid JSON") from None

    def validate_sessions(self) -> None:
        for name in ("admin", "alice", "bob", "reader"):
            identity = self.json(name, "GET", "/auth-api/me", label=f"Validate {name} Identity session")
            identity_user = identity.get("user") if isinstance(identity, dict) else None
            response = self.request(name, "GET", "/api/me", label=f"Validate {name} session")
            try:
                actor = response.json()
            except ValueError:
                raise AcceptanceError(f"Saved synthetic {name} session returned invalid identity data") from None
            principal_id = actor.get("id") if isinstance(actor, dict) else None
            if not isinstance(principal_id, str) or not principal_id:
                raise AcceptanceError(f"Saved synthetic {name} session is not authorized")
            run_id = self.resources["identity_run_id"]
            expected_name = f"QA {name.title()} {run_id}"
            expected_email = f"collab-{name}-{run_id}@example.com"
            if not isinstance(identity_user, dict):
                raise AcceptanceError(f"Saved synthetic {name} session is missing its Identity account")
            if (
                identity_user.get("name") != expected_name
                or identity_user.get("email") != expected_email
                or actor.get("name") != identity_user.get("name")
                or actor.get("kind") != "human"
            ):
                raise AcceptanceError(f"Saved synthetic {name} session does not match its Identity run, name and email")
            self.principals[name] = principal_id
            self.check(f"session_{name}_matches_identity_run_name_and_email", True)

    def create(self, actor: str, path: str, body: dict[str, Any], *, expected: int = 201, label: str, product_prefix: str = "") -> dict[str, Any]:
        value = self.json(actor, "POST", path, body=body, expected=expected, label=label, product_prefix=product_prefix)
        if not isinstance(value, dict):
            raise AcceptanceError(f"{label}: unexpected response shape")
        return value

    def verify_work_postgres(self) -> None:
        code = "from sqlalchemy.engine.url import make_url; from ordivant.config import database_url; print(make_url(database_url()).get_backend_name())"
        command = [
            "docker", "compose", "--project-directory", str(ROOT),
            "--project-name", QA_COMPOSE_PROJECT, "--file", str(ROOT / "compose.yaml"),
            "exec", "-T", "work-api", "python", "-c", code,
        ]
        try:
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise AcceptanceError("Could not verify the QA Work database backend") from None
        if result.returncode != 0:
            raise AcceptanceError("Could not verify the QA Work database backend")
        backend = result.stdout.strip()
        self.check("claim_race_uses_postgresql", backend == "postgresql")
        if backend != "postgresql":
            raise AcceptanceError("The dedicated Work QA service is not using PostgreSQL")

    def active_sprint_race(self, project_id: str) -> None:
        planning = self.json("admin", "GET", f"/api/projects/{project_id}/planning", label="Read active Sprint race precondition")
        sprints = planning.get("sprints") if isinstance(planning, dict) else None
        if not isinstance(sprints, list):
            raise AcceptanceError("Planning API returned an invalid Sprint list")
        active = [item for item in sprints if isinstance(item, dict) and item.get("status") == "active"]
        for sprint in active:
            if not str(sprint.get("name", "")).startswith("P0P1-"):
                raise AcceptanceError("An existing non-QA active Sprint prevents the isolated concurrency test")
            self.json("admin", "PATCH", f"/api/sprints/{sprint['id']}", body={"status": "closed"}, label="Close prior P0P1 active Sprint")

        participants = self.json("admin", "GET", f"/api/projects/{project_id}/participants", label="Read Sprint race managers")
        roles = {
            item.get("id"): item.get("role")
            for item in participants
            if isinstance(item, dict)
        } if isinstance(participants, list) else {}
        manager_ids = {name: self.principals[name] for name in ("admin", "bob")}
        authorized = all(roles.get(principal_id) in {"admin", "manager"} for principal_id in manager_ids.values())
        distinct = len(set(manager_ids.values())) == 2
        self.check("active_sprint_race_has_two_distinct_project_managers", authorized and distinct)
        if not authorized or not distinct:
            raise AcceptanceError("Two distinct authorized manager sessions are required for the Sprint race")

        start_at = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=2)
        path = f"/api/projects/{project_id}/sprints"

        def create_active(actor: str) -> tuple[str, httpx.Response]:
            payload = {
                "name": f"{self.prefix} Active Sprint {actor}",
                "goal": "Synthetic concurrent active Sprint acceptance.",
                "start_at": start_at.isoformat(),
                "end_at": (start_at + timedelta(days=7)).isoformat(),
                "status": "active",
            }
            try:
                response = self.clients[actor].post(
                    path,
                    json=payload,
                    headers={"Idempotency-Key": f"qa-p0p1-{self.run_id}-active-sprint-{actor}"},
                )
            except httpx.HTTPError:
                raise AcceptanceError("Concurrent active Sprint request failed") from None
            return actor, response

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = dict(pool.map(create_active, ("admin", "bob")))
        except Exception as error:
            if isinstance(error, AcceptanceError):
                raise
            raise AcceptanceError("Concurrent active Sprint requests failed") from None

        statuses = {name: response.status_code for name, response in responses.items()}
        winners = [name for name, response in responses.items() if response.status_code == 201]
        conflicts = [name for name, response in responses.items() if response.status_code == 409]
        self.check("concurrent_active_sprint_has_one_success_and_one_conflict", len(winners) == 1 and len(conflicts) == 1)
        if len(winners) != 1 or len(conflicts) != 1:
            raise AcceptanceError(f"Concurrent active Sprint statuses were {statuses}")

        try:
            created = responses[winners[0]].json()
        except ValueError:
            raise AcceptanceError("Winning active Sprint response was invalid") from None
        sprint_id = created.get("id") if isinstance(created, dict) else None
        self.check("concurrent_active_sprint_winner_is_active", created.get("status") == "active" and isinstance(sprint_id, str))
        if not isinstance(sprint_id, str):
            raise AcceptanceError("Winning active Sprint response did not include its ID")
        self.resources["active_race_sprint_id"] = sprint_id
        self.resources["active_race_sprint_statuses"] = statuses
        self.json("admin", "PATCH", f"/api/sprints/{sprint_id}", body={"status": "closed"}, label="Close Sprint race winner")
        after = self.json("admin", "GET", f"/api/projects/{project_id}/planning", label="Verify active Sprint race cleanup")
        still_active = [
            item for item in after.get("sprints", [])
            if isinstance(item, dict) and item.get("status") == "active" and str(item.get("name", "")).startswith("P0P1-")
        ] if isinstance(after, dict) else []
        self.check("active_sprint_race_leaves_no_test_sprint_active", not still_active)

    def claim_race(self, project_id: str) -> None:
        task = self.create("admin", "/api/tasks", {
            "project_id": project_id,
            "title": f"{self.prefix} concurrent human claim task",
            "goal": "Prove PostgreSQL allows one human claim and blocks the losing actor.",
            "acceptance_criteria": ["Only one human claim succeeds", "The losing actor cannot update the execution"],
            "status": "ready",
            "reviewer_principal_id": self.principals["admin"],
        }, label="Create unassigned claim race task")
        task_id = task.get("id")
        self.check(
            "claim_race_task_is_ready_unassigned_with_independent_reviewer",
            isinstance(task_id, str)
            and task.get("status") == "ready"
            and task.get("assignee_principal_id") is None
            and task.get("assignee_id") is None
            and task.get("reviewer_principal_id") == self.principals["admin"],
        )
        if not isinstance(task_id, str):
            raise AcceptanceError("Claim race task did not include its ID")

        claim_names = ("alice", "bob")

        def claim_as(actor: str) -> tuple[str, httpx.Response]:
            try:
                response = self.clients[actor].post(
                    f"/api/tasks/{task_id}/claim",
                    json={},
                    headers={"Idempotency-Key": f"qa-p0p1-{self.run_id}-claim-race-{actor}"},
                )
            except httpx.HTTPError:
                raise AcceptanceError("Concurrent human claim request failed") from None
            return actor, response

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = dict(pool.map(claim_as, claim_names))
        except Exception as error:
            if isinstance(error, AcceptanceError):
                raise
            raise AcceptanceError("Concurrent human claim requests failed") from None
        statuses = {name: response.status_code for name, response in responses.items()}
        winners = [name for name, response in responses.items() if response.status_code == 200]
        denied = [name for name, response in responses.items() if response.status_code in {403, 409}]
        self.check("claim_race_has_one_200_and_one_403_or_409", len(winners) == 1 and len(denied) == 1)
        if len(winners) != 1 or len(denied) != 1:
            raise AcceptanceError(f"Concurrent human claim statuses were {statuses}")

        winner = winners[0]
        loser = next(name for name in claim_names if name != winner)
        try:
            claim = responses[winner].json()
        except ValueError:
            raise AcceptanceError("Winning human claim response was invalid") from None
        execution = claim.get("execution") if isinstance(claim, dict) else None
        execution_id = execution.get("id") if isinstance(execution, dict) else None
        self.check(
            "claim_race_winner_is_human_without_agent_lease",
            isinstance(execution_id, str)
            and execution.get("executor_kind") == "human"
            and execution.get("agent_id") is None
            and claim.get("lease_token") is None,
        )
        if not isinstance(execution_id, str):
            raise AcceptanceError("Winning human claim did not include its execution ID")

        before_rows = self.json(winner, "GET", f"/api/tasks/{task_id}/executions", label="Read claim race execution before loser update")
        before = next((item for item in before_rows if isinstance(item, dict) and item.get("id") == execution_id), None) if isinstance(before_rows, list) else None
        self.check("claim_race_persists_exactly_one_execution", isinstance(before_rows, list) and len(before_rows) == 1 and before is not None)
        if before is None:
            raise AcceptanceError("Winning human execution was not persisted")

        try:
            loser_progress = self.clients[loser].post(
                f"/api/tasks/{task_id}/progress",
                json={"execution_id": execution_id, "progress": 99, "summary": f"Forbidden loser update {self.run_id}."},
                headers={"Idempotency-Key": f"qa-p0p1-{self.run_id}-claim-race-loser-update"},
            )
        except httpx.HTTPError:
            raise AcceptanceError("Loser execution write request failed") from None
        after_rows = self.json(winner, "GET", f"/api/tasks/{task_id}/executions", label="Read claim race execution after loser update")
        after = next((item for item in after_rows if isinstance(item, dict) and item.get("id") == execution_id), None) if isinstance(after_rows, list) else None
        task_after = self.json(winner, "GET", f"/api/tasks/{task_id}", label="Read claim race task after loser update")
        invariants = {
            "claim_race_loser_cannot_write_execution": loser_progress.status_code in {403, 409},
            "claim_race_loser_update_leaves_execution_unchanged": after is not None
            and after.get("progress") == before.get("progress")
            and after.get("summary") == before.get("summary")
            and task_after.get("progress") == before.get("progress"),
        }
        self.checks.update(invariants)
        if not all(invariants.values()):
            raise AcceptanceError("Concurrent claim loser-write invariants failed")
        self.resources.update(
            claim_race_task_id=task_id,
            claim_race_winner=winner,
            claim_race_loser=loser,
            claim_race_statuses=statuses,
        )

    def epic_hierarchy_race(self, project_id: str) -> None:
        epics: dict[str, dict[str, Any]] = {}
        for label, actor in (('a', 'admin'), ('b', 'bob')):
            epics[label] = self.create(actor, "/api/tasks", {
                "project_id": project_id,
                "title": f"{self.prefix} Epic {label.upper()}",
                "description": "Synthetic concurrent Epic hierarchy acceptance.",
                "goal": "Verify project-scoped locking prevents concurrent Epic cycles.",
                "acceptance_criteria": ["At most one reciprocal parent link succeeds"],
                "status": "backlog",
                "work_type": "epic",
            }, label=f"Create concurrent Epic {label.upper()}")
        epic_a_id = epics["a"].get("id")
        epic_b_id = epics["b"].get("id")
        distinct = isinstance(epic_a_id, str) and isinstance(epic_b_id, str) and epic_a_id != epic_b_id
        self.check("epic_hierarchy_race_has_two_distinct_epics", distinct)
        if not distinct:
            raise AcceptanceError("Concurrent Epic hierarchy fixtures are invalid")

        operations = (("admin", epic_a_id, epic_b_id), ("bob", epic_b_id, epic_a_id))

        def set_parent(operation: tuple[str, str, str]) -> tuple[str, str, httpx.Response]:
            actor, task_id, parent_id = operation
            try:
                response = self.clients[actor].patch(
                    f"/api/tasks/{task_id}",
                    json={"epic_id": parent_id},
                    headers={"Idempotency-Key": f"qa-p0p1-{self.run_id}-epic-cycle-{actor}"},
                )
            except httpx.HTTPError:
                raise AcceptanceError("Concurrent Epic hierarchy update failed") from None
            return actor, task_id, response

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(set_parent, operations))
        except Exception as error:
            if isinstance(error, AcceptanceError):
                raise
            raise AcceptanceError("Concurrent Epic hierarchy updates failed") from None

        statuses = {actor: response.status_code for actor, _task_id, response in results}
        successes = [actor for actor, _task_id, response in results if response.status_code == 200]
        conflicts = [actor for actor, _task_id, response in results if response.status_code == 409]
        self.check("epic_hierarchy_race_has_one_success_and_one_conflict", len(successes) == 1 and len(conflicts) == 1)
        if len(successes) != 1 or len(conflicts) != 1:
            raise AcceptanceError(f"Concurrent Epic hierarchy statuses were {statuses}")

        final_a = self.json("admin", "GET", f"/api/tasks/{epic_a_id}", label="Verify concurrent Epic A hierarchy")
        final_b = self.json("admin", "GET", f"/api/tasks/{epic_b_id}", label="Verify concurrent Epic B hierarchy")
        reciprocal_cycle = final_a.get("epic_id") == epic_b_id and final_b.get("epic_id") == epic_a_id
        self.check("epic_hierarchy_race_leaves_no_reciprocal_cycle", not reciprocal_cycle)
        if reciprocal_cycle:
            raise AcceptanceError("Concurrent Epic hierarchy updates formed a reciprocal cycle")
        self.resources.update(epic_hierarchy_race_ids={"a": epic_a_id, "b": epic_b_id}, epic_hierarchy_race_statuses=statuses)

    def run_acceptance(self) -> dict[str, Any]:
        self.validate_target()
        self.verify_compose_scope()
        context = self.load_context()
        self.validate_sessions()
        project_id = self.resources["project_id"]
        space_id = self.resources["knowledge_space_id"]
        alice_id = self.principals["alice"]
        bob_id = self.principals["bob"]
        self.check("reviewer_is_independent_of_worker", alice_id != bob_id)

        self.verify_work_postgres()
        self.active_sprint_race(project_id)
        self.epic_hierarchy_race(project_id)
        self.claim_race(project_id)

        tomorrow = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        sprint = self.create("admin", f"/api/projects/{project_id}/sprints", {
            "name": f"{self.prefix} Sprint", "goal": "Synthetic planning acceptance.",
            "start_at": tomorrow.isoformat(), "end_at": (tomorrow + timedelta(days=7)).isoformat(), "status": "planned",
        }, label="Create Sprint")
        self.resources["sprint_id"] = sprint.get("id")
        self.resources["sprint_name"] = sprint.get("name")
        self.check("sprint_created_with_dates", isinstance(sprint.get("id"), str) and sprint.get("start_at") and sprint.get("end_at"))

        milestone = self.create("admin", f"/api/projects/{project_id}/milestones", {
            "name": f"{self.prefix} Milestone", "description": "Synthetic planning acceptance.",
            "due_at": (tomorrow + timedelta(days=7)).isoformat(), "status": "open",
        }, label="Create milestone")
        self.resources["milestone_id"] = milestone.get("id")
        self.check("milestone_created", isinstance(milestone.get("id"), str))

        field_key = f"qa_{self.run_id}_note"
        field = self.create("admin", f"/api/projects/{project_id}/fields", {
            "key": field_key, "name": f"{self.prefix} note", "kind": "text", "required": False, "options": [], "active": True,
        }, label="Create custom field")
        self.resources["field_id"] = field.get("id")
        self.resources["field_key"] = field_key
        self.check("custom_field_created", field.get("key") == field_key)

        stage = self.create("admin", f"/api/projects/{project_id}/stages", {
            "name": f"{self.prefix} Ready", "category": "ready", "rank": 100, "active": True,
        }, label="Create planning stage")
        self.resources["stage_id"] = stage.get("id")
        self.check("custom_stage_created", stage.get("category") == "ready")

        rule_label = f"rule-{self.run_id}"
        rule = self.create("admin", f"/api/projects/{project_id}/rules", {
            "name": f"{self.prefix} created rule", "event": "task.created",
            "conditions": {"work_type": "task"}, "action": "label",
            "parameters": {"label": rule_label}, "enabled": True,
        }, label="Create event rule")
        self.resources["rule_id"] = rule.get("id")
        self.check("event_rule_created", rule.get("event") == "task.created" and rule.get("action") == "label")

        form = self.create("admin", f"/api/projects/{project_id}/forms", {
            "name": f"{self.prefix} intake", "description": "Synthetic member intake acceptance.",
            "work_type": "task", "fields": [field_key], "active": True,
        }, label="Create authenticated intake form")
        self.resources["form_id"] = form.get("id")
        self.check("intake_form_created", form.get("fields") == [field_key])
        submitted_intake = self.create("alice", f"/api/forms/{form['id']}/submit", {
            "title": f"{self.prefix} intake submission", "description": "Synthetic intake submission.",
            "custom_fields": {field_key: self.prefix},
        }, label="Submit authenticated intake")
        intake_task = submitted_intake.get("task") if isinstance(submitted_intake.get("task"), dict) else submitted_intake
        self.resources["intake_task_id"] = intake_task.get("id")
        self.check("authenticated_intake_created_backlog_task", intake_task.get("status") == "backlog" and intake_task.get("custom_fields", {}).get(field_key) == self.prefix)

        task_body = {
            "project_id": project_id,
            "title": f"{self.prefix} assigned lifecycle task",
            "description": "Synthetic task for a human claim, evidence submission and independent review.",
            "goal": "Verify the existing Work lifecycle without an LLM.",
            "acceptance_criteria": ["Alice claims as a human", "Bob independently accepts evidence"],
            "priority": "medium", "status": "ready", "work_type": "task",
            "assignee_principal_id": alice_id, "reviewer_principal_id": bob_id,
            "sprint_id": sprint["id"], "milestone_id": milestone["id"], "stage_id": stage["id"],
            "estimate_points": 3, "custom_fields": {field_key: self.prefix},
            "due_at": (tomorrow + timedelta(days=3)).isoformat(),
        }
        lifecycle_task = self.create("admin", "/api/tasks", task_body, label="Create human lifecycle task")
        self.resources["lifecycle_task_id"] = lifecycle_task.get("id")
        self.resources["lifecycle_task_key"] = lifecycle_task.get("key")
        self.check("task_metadata_links_sprint_stage_and_field", lifecycle_task.get("sprint_id") == sprint.get("id") and lifecycle_task.get("stage_id") == stage.get("id") and lifecycle_task.get("custom_fields", {}).get(field_key) == self.prefix)
        self.check("event_rule_applied_to_task", rule_label in lifecycle_task.get("labels", []))

        ui_task_body = {**task_body, "title": f"{self.prefix} browser collaboration task", "description": "Synthetic browser check for Work board and CollaborationPanel."}
        ui_task = self.create("admin", "/api/tasks", ui_task_body, label="Create browser task")
        self.resources["browser_task_id"] = ui_task.get("id")
        self.resources["browser_task_key"] = ui_task.get("key")
        self.resources["browser_task_title"] = ui_task.get("title")

        isolated_project = self.resources.get("isolated_project_id")
        if not isinstance(isolated_project, str):
            raise AcceptanceError("Saved isolated Work project ID is missing")
        isolated_task = self.create("admin", "/api/tasks", {
            "project_id": isolated_project, "title": f"{self.prefix} isolated-only task", "goal": "Synthetic cross-scope search fixture.",
        }, label="Create isolated scope search fixture")
        self.resources["isolated_task_id"] = isolated_task.get("id")

        search_doc = self.create("alice", "/api/documents", {
            "space_id": space_id, "title": f"{self.prefix} Knowledge search result",
            "summary": "Synthetic cross-product search fixture.", "body": f"{self.prefix} searchable Knowledge body.",
            "change_summary": "Initial synthetic QA document.",
        }, label="Create Knowledge search fixture", product_prefix="/knowledge-api")
        document = search_doc.get("document") if isinstance(search_doc.get("document"), dict) else search_doc
        self.resources["knowledge_document_id"] = document.get("id")
        self.resources["knowledge_document_title"] = document.get("title")
        self.check("knowledge_search_fixture_created_in_authorized_space", isinstance(document.get("id"), str))

        work_hits = self.json("alice", "GET", "/api/tasks", params={"q": self.prefix}, label="Search scoped Work tasks")
        knowledge_hits = self.json("alice", "GET", "/api/documents", params={"q": self.prefix}, label="Search scoped Knowledge documents", product_prefix="/knowledge-api")
        if not isinstance(work_hits, list) or not isinstance(knowledge_hits, list):
            raise AcceptanceError("Cross-product search returned an unexpected response shape")
        self.check("work_search_finds_authorized_project_task", any(item.get("id") == ui_task.get("id") for item in work_hits if isinstance(item, dict)))
        self.check("work_search_excludes_unassigned_project", all(item.get("id") != isolated_task.get("id") for item in work_hits if isinstance(item, dict)))
        self.check("knowledge_search_finds_authorized_space_document", any(item.get("id") == document.get("id") for item in knowledge_hits if isinstance(item, dict)))

        claim = self.json("alice", "POST", f"/api/tasks/{lifecycle_task['id']}/claim", body={}, label="Alice human claim")
        execution = claim.get("execution") if isinstance(claim.get("execution"), dict) else {}
        execution_id = execution.get("id")
        self.check("human_claim_has_no_agent_lease", execution.get("executor_kind") == "human" and execution.get("agent_id") is None and claim.get("lease_token") is None)
        if not isinstance(execution_id, str):
            raise AcceptanceError("Human claim did not return an execution ID")
        self.json("alice", "POST", f"/api/tasks/{lifecycle_task['id']}/progress", body={
            "execution_id": execution_id, "progress": 65, "summary": f"{self.prefix} human progress update.",
        }, label="Alice progress update")
        now = datetime.now(UTC).replace(microsecond=0)
        worklog = self.create("alice", f"/api/tasks/{lifecycle_task['id']}/worklogs", {
            "minutes": 37, "started_at": now.isoformat(), "description": f"{self.prefix} synthetic worklog.",
        }, expected=201, label="Record Alice worklog")
        self.check("worklog_created_for_human_capacity_report", isinstance(worklog.get("id"), str))
        submitted = self.json("alice", "POST", f"/api/tasks/{lifecycle_task['id']}/submit", body={
            "execution_id": execution_id, "summary": f"{self.prefix} Alice completed the work.",
            "artifacts": [{"kind": "summary", "title": f"{self.prefix} evidence", "content": "Synthetic acceptance evidence."}],
        }, label="Alice submits evidence")
        self.check("evidence_submission_enters_review", submitted.get("task", {}).get("status") == "in_review")
        denied_self_review = self.clients["alice"].post(f"/api/tasks/{lifecycle_task['id']}/review", json={"decision": "accept", "comment": "Self-review is forbidden."}, headers={"Idempotency-Key": f"qa-p0p1-{self.run_id}-self-review"})
        self.check("submitter_cannot_self_review", denied_self_review.status_code == 403)
        reviewed = self.json("bob", "POST", f"/api/tasks/{lifecycle_task['id']}/review", body={
            "decision": "accept", "comment": f"{self.prefix} independent review passed.",
        }, label="Bob independent review")
        self.check("independent_review_completes_task", reviewed.get("task", {}).get("status") == "done")

        participants = self.json("alice", "GET", f"/api/collaboration/task/{ui_task['id']}/participants", label="Read collaboration participants")
        if not isinstance(participants, list):
            raise AcceptanceError("Collaboration participant list is invalid")
        bob_participant = next((item for item in participants if isinstance(item, dict) and item.get("id") == bob_id), None)
        if bob_participant is None:
            raise AcceptanceError("Bob is not available as a scoped collaboration participant")

        attachment_bytes = f"{self.prefix} safe synthetic attachment".encode("utf-8")
        attachment = self.create("alice", f"/api/collaboration/task/{ui_task['id']}/attachments", {
            "filename": f"{self.run_id}.txt", "content_base64": base64.b64encode(attachment_bytes).decode("ascii"),
        }, label="Upload same-hash attachment")
        downloaded = self.request("alice", "GET", f"/api/collaboration/attachments/{attachment.get('id')}/download", label="Download same-hash attachment")
        actual_hash = hashlib.sha256(downloaded.content).hexdigest()
        self.check("attachment_download_matches_sha256", actual_hash == attachment.get("sha256") and downloaded.content == attachment_bytes)
        reader_list = self.clients["reader"].get(f"/api/collaboration/task/{ui_task['id']}/attachments")
        reader_download = self.clients["reader"].get(f"/api/collaboration/attachments/{attachment.get('id')}/download")
        self.check("attachment_list_denied_across_work_scope", reader_list.status_code in {403, 404})
        self.check("attachment_download_denied_across_work_scope", reader_download.status_code in {403, 404})

        mention_body = f"{self.prefix} Alice mentions Bob for review."
        self.json("alice", "POST", f"/api/collaboration/task/{ui_task['id']}/discussion", body={
            "body": mention_body, "mention_ids": [bob_id],
        }, expected=201, label="Alice mentions Bob")
        bob_notices = self.json("bob", "GET", "/api/collaboration/notifications", label="Read Bob notification center")
        notice = next((item for item in bob_notices if isinstance(item, dict) and item.get("resource_id") == ui_task["id"] and item.get("body") == mention_body), None) if isinstance(bob_notices, list) else None
        self.check("mention_creates_bob_notification", notice is not None and str(notice.get("event", "")).startswith("discussion."))
        self.resources["mention_body"] = mention_body
        self.resources["notification_id"] = notice.get("id") if isinstance(notice, dict) else None

        capacity = self.json("admin", "POST", f"/api/projects/{project_id}/capacity", body={
            "principal_id": alice_id, "weekly_minutes": 1800,
        }, label="Set Alice weekly capacity")
        self.check("weekly_capacity_saved", capacity.get("principal_id") == alice_id and capacity.get("weekly_minutes") == 1800)
        reports = self.json("admin", "GET", f"/api/projects/{project_id}/reports", label="Read Work reports")
        alice_capacity = next((row for row in reports.get("capacity", []) if isinstance(row, dict) and row.get("principal_id") == alice_id), None) if isinstance(reports, dict) else None
        self.check("reports_match_capacity_and_worklog_schema", isinstance(reports, dict) and isinstance(reports.get("totals", {}).get("by_status"), dict) and isinstance(reports.get("capacity"), list) and isinstance(reports.get("worklogs"), dict))
        self.check("reports_include_weekly_capacity_and_observed_work", isinstance(alice_capacity, dict) and alice_capacity.get("weekly_minutes") == 1800 and alice_capacity.get("observed_minutes", 0) >= 37 and alice_capacity.get("assigned_estimate_points", 0) >= 0)
        self.check("cycle_time_reports_observed_basis", isinstance(reports, dict) and reports.get("cycle_time", {}).get("basis") == "task first execution start to accepted review")

        csv_response = self.request("admin", "GET", f"/api/projects/{project_id}/tasks/export", label="Export task CSV")
        try:
            rows = list(csv.DictReader(io.StringIO(csv_response.text, newline="")))
        except csv.Error:
            raise AcceptanceError("CSV export was not parseable") from None
        self.check("csv_export_contains_synthetic_work", any(row.get("title") == ui_task.get("title") for row in rows))
        csv_output = io.StringIO(newline="")
        fieldnames = ["title", "description", "work_type", "priority", "status", "due_at", "start_at", "estimate_points", "epic_id", "sprint_id", "milestone_id", "labels", "custom_fields"]
        writer = csv.DictWriter(csv_output, fieldnames=fieldnames, lineterminator="\r\n")
        writer.writeheader()
        writer.writerow({"title": f"{self.prefix} CSV import task", "description": "Synthetic CSV import.", "work_type": "task", "priority": "low", "status": "backlog", "labels": "[]", "custom_fields": json.dumps({field_key: self.prefix})})
        imported = self.json("admin", "POST", f"/api/projects/{project_id}/tasks/import", body={"csv": csv_output.getvalue()}, label="Import task CSV")
        created_rows = imported.get("created", []) if isinstance(imported, dict) else []
        self.resources["csv_task_id"] = created_rows[0].get("id") if created_rows and isinstance(created_rows[0], dict) else None
        self.check("csv_import_creates_task", len(created_rows) == 1 and not imported.get("errors"))

        query_name = f"{self.prefix} Saved query"
        saved_query = self.create("alice", "/api/saved-queries", {
            "name": query_name, "project_id": project_id,
            "filters": {"q": self.prefix, "status": "ready", "work_type": "task", "sprint_id": sprint["id"]},
        }, label="Create saved task query")
        self.resources["saved_query_id"] = saved_query.get("id")
        self.resources["saved_query_name"] = query_name
        query_rows = self.json("alice", "GET", "/api/saved-queries", label="List saved task queries")
        self.check("saved_query_persists_backend_filter_shape", saved_query.get("filters", {}).get("q") == self.prefix and any(item.get("id") == saved_query.get("id") for item in query_rows if isinstance(item, dict)))

        order_key = f"{self.prefix}-ORDER"
        order_a = self.create("admin", "/api/tasks", {"project_id": project_id, "title": f"{order_key}-A", "status": "backlog", "goal": "Synthetic backlog ordering."}, label="Create first backlog order task")
        order_hidden = self.create("admin", "/api/tasks", {"project_id": project_id, "title": f"{self.prefix} hidden backlog neighbor", "status": "backlog", "goal": "Synthetic hidden ordering neighbor."}, label="Create hidden backlog order neighbor")
        order_b = self.create("admin", "/api/tasks", {"project_id": project_id, "title": f"{order_key}-B", "status": "backlog", "goal": "Synthetic backlog ordering."}, label="Create second backlog order task")
        ordered = self.json("admin", "POST", f"/api/projects/{project_id}/reorder", body={"task_ids": [order_a["id"], order_hidden["id"], order_b["id"]]}, label="Initialize backlog order with hidden neighbor")
        all_tasks = self.json("admin", "GET", "/api/tasks", params={"project_id": project_id}, label="Verify backlog ordering fixture")
        positions = {item.get("id"): index for index, item in enumerate(all_tasks) if isinstance(item, dict)}
        self.check("backlog_order_fixture_persisted", isinstance(ordered, list) and len(ordered) == 3)
        self.check("backlog_hidden_fixture_between_visible_tasks", positions.get(order_a["id"], -1) < positions.get(order_hidden["id"], -1) < positions.get(order_b["id"], -1))

        self.resources.update(order_key=order_key, order_a_id=order_a.get("id"), order_a_key=order_a.get("key"), order_hidden_id=order_hidden.get("id"), order_hidden_key=order_hidden.get("key"), order_b_id=order_b.get("id"), order_b_key=order_b.get("key"))
        self.check("planning_runs_without_llm_or_agent_run", True)
        output_context = {
            "base_url": QA_BASE_URL, "compose_project": QA_COMPOSE_PROJECT, "run_id": self.run_id, "prefix": self.prefix,
            "work_principal_ids": self.principals.copy(),
            "project_id": project_id, "sprint_id": self.resources["sprint_id"], "sprint_name": self.resources["sprint_name"],
            "active_race_sprint_id": self.resources["active_race_sprint_id"],
            "claim_race_task_id": self.resources["claim_race_task_id"],
            "field_key": field_key, "stage_id": self.resources["stage_id"], "query_name": query_name,
            "browser_task_id": ui_task["id"], "browser_task_key": ui_task.get("key"), "browser_task_title": ui_task["title"],
            "lifecycle_task_id": lifecycle_task["id"], "knowledge_document_id": document["id"],
            "knowledge_document_title": document.get("title"), "mention_body": mention_body, "notification_id": self.resources["notification_id"],
            "isolated_task_id": self.resources["isolated_task_id"],
            "order_key": order_key, "order_a_id": order_a["id"], "order_a_key": order_a.get("key"),
            "order_hidden_id": order_hidden["id"], "order_hidden_key": order_hidden.get("key"),
            "order_b_id": order_b["id"], "order_b_key": order_b.get("key"),
        }
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "context.json").write_text(json.dumps(output_context, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return output_context

    def close(self) -> None:
        for client in self.clients.values():
            client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=QA_BASE_URL)
    parser.add_argument("--project", default=QA_COMPOSE_PROJECT)
    args = parser.parse_args()
    run = PlanningAcceptance(args.base_url, args.project)
    report: dict[str, Any] = {
        "status": "failed", "base_url": QA_BASE_URL, "compose_project": QA_COMPOSE_PROJECT,
        "run_id": run.run_id, "prefix": run.prefix, "checks": run.checks,
    }
    try:
        output_context = run.run_acceptance()
        report["status"] = "passed"
        report["resource_ids"] = {key: value for key, value in output_context.items() if key.endswith("_id") and isinstance(value, str)}
    except AcceptanceError as error:
        report["failure"] = str(error)
    except Exception as error:
        report["failure"] = type(error).__name__
    finally:
        run.close()
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "api-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"P0P1_API_ACCEPTANCE_{report['status'].upper()} checks={len(run.checks)} report=.cache/p0-p1-qa/api-report.json")
    if report["status"] != "passed":
        print(f"Failure: {report.get('failure', 'acceptance failed')}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
