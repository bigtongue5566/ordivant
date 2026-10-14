from __future__ import annotations

import ast
import re
from urllib.parse import urlsplit

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import service
from .errors import DomainError
from .config import load_gitea_config
from .deployments import deployments_for
from .gitea import GiteaClient
from .models import (
    Principal,
    Project,
    PullRequest,
    PullRequestInlineComment,
    Repository,
    ScopeMembership,
)
from .schemas import PullRequestInlineCommentCreate, PullRequestInlineReplyCreate, PullRequestInlineResolve
from .security import new_id, now_utc

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _excerpt(value: str, limit: int = 220) -> str:
    plain = re.sub(r"[`*_#>\[\]()]+", "", value or "")
    plain = " ".join(plain.split())
    return plain[:limit]


def search(session: Session, principal: Principal, query: str) -> list[dict]:
    term = query.strip()
    if not term:
        return []
    visible_projects = (
        select(Project.id)
        .join(ScopeMembership, ScopeMembership.scope_id == Project.scope_id)
        .where(
            Project.organization_id == principal.organization_id,
            ScopeMembership.principal_id == principal.id,
        )
    )
    pattern = f"%{term}%"
    results: list[dict] = []
    for project in session.scalars(select(Project).where(
        Project.id.in_(visible_projects),
        or_(Project.key.ilike(pattern), Project.name.ilike(pattern), Project.description.ilike(pattern)),
    ).order_by(Project.name).limit(50)).all():
        results.append({"id": project.id, "resource_kind": "project", "title": f"{project.key} · {project.name}", "excerpt": _excerpt(project.description), "source": "code_index"})

    for repository in session.scalars(
        select(Repository).join(Project, Project.id == Repository.project_id)
        .where(
            Project.id.in_(visible_projects),
            or_(Repository.owner.ilike(pattern), Repository.name.ilike(pattern)),
        ).order_by(Repository.owner, Repository.name).limit(50)
    ).all():
        results.append({"id": repository.id, "resource_kind": "repository", "title": f"{repository.owner}/{repository.name}", "excerpt": "Gitea repository", "source": "code_index"})

    for pull in session.scalars(
        select(PullRequest).join(Repository, Repository.id == PullRequest.repository_id)
        .join(Project, Project.id == Repository.project_id)
        .where(
            Project.id.in_(visible_projects),
            or_(PullRequest.title.ilike(pattern), PullRequest.body.ilike(pattern)),
        ).order_by(PullRequest.updated_at.desc()).limit(50)
    ).all():
        results.append({"id": pull.id, "resource_kind": "pull", "title": f"PR #{pull.number} · {pull.title}", "excerpt": _excerpt(pull.body), "source": "code_index"})
    return results[:100]


def pull_by_id(session: Session, principal: Principal, pull_id: str) -> dict:
    pull = session.get(PullRequest, pull_id)
    if pull is None:
        raise DomainError(404, "not_found", "Pull request not found")
    repository = session.get(Repository, pull.repository_id)
    if repository is None:
        raise DomainError(404, "not_found", "Pull request not found")
    service.require_repository(session, principal, repository.id)
    return {**service.get_pull(session, principal, repository.id, pull.number), "project_id": repository.project_id}


def resolve_resource(session: Session, principal: Principal, resource_kind: str, resource_id: str) -> dict:
    if resource_kind == "project":
        project = service.require_project(session, principal, resource_id)
        return {"resource_kind": resource_kind, "id": project.id, "project_id": project.id}
    if resource_kind == "repository":
        repository, project = service.require_repository(session, principal, resource_id)
        return {"resource_kind": resource_kind, "id": repository.id, "project_id": project.id, "repository_id": repository.id}
    if resource_kind == "pull":
        pull = session.get(PullRequest, resource_id)
        if pull is None:
            raise DomainError(404, "not_found", "Pull request not found")
        repository, project = service.require_repository(session, principal, pull.repository_id)
        return {
            "resource_kind": resource_kind, "id": pull.id, "project_id": project.id,
            "repository_id": repository.id, "pull_number": pull.number,
        }
    raise DomainError(404, "not_found", "Code resource not found")


def _diff_path(value: str, prefix: str) -> str | None:
    value = value.rstrip("\r\n").split("\t", 1)[0]
    if value == "/dev/null":
        return None
    if value.startswith('"'):
        try:
            value = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return None
    if not isinstance(value, str) or not value.startswith(prefix):
        return None
    path = value[len(prefix):]
    if not path or path.startswith("/") or "\\" in path or "\x00" in path or any(part in {"", ".", ".."} for part in path.split("/")) or any(part.lower() == ".git" for part in path.split("/")):
        return None
    return path


def parse_unified_diff(diff: str) -> dict[str, dict[str, set[int]]]:
    files: dict[str, dict[str, set[int]]] = {}
    old_path: str | None = None
    new_path: str | None = None
    old_line = new_line = 0
    in_hunk = False

    for line in diff.splitlines():
        if line.startswith("diff --git "):
            old_path = new_path = None
            in_hunk = False
            continue
        if not in_hunk and line.startswith("--- "):
            old_path = _diff_path(line[4:], "a/")
            in_hunk = False
            continue
        if not in_hunk and line.startswith("+++ "):
            new_path = _diff_path(line[4:], "b/")
            for path in {old_path, new_path} - {None}:
                files.setdefault(path, {"LEFT": set(), "RIGHT": set()})
            in_hunk = False
            continue
        match = _HUNK.match(line)
        if match:
            old_line = int(match.group(1))
            new_line = int(match.group(3))
            in_hunk = True
            continue
        if not in_hunk or old_path is None and new_path is None:
            continue
        if line.startswith("\\ No newline at end of file"):
            continue
        if line.startswith(" "):
            if old_path is not None:
                files.setdefault(old_path, {"LEFT": set(), "RIGHT": set()})["LEFT"].add(old_line)
            if new_path is not None:
                files.setdefault(new_path, {"LEFT": set(), "RIGHT": set()})["RIGHT"].add(new_line)
            old_line += 1
            new_line += 1
        elif line.startswith("-"):
            if old_path is not None:
                files.setdefault(old_path, {"LEFT": set(), "RIGHT": set()})["LEFT"].add(old_line)
            old_line += 1
        elif line.startswith("+"):
            if new_path is not None:
                files.setdefault(new_path, {"LEFT": set(), "RIGHT": set()})["RIGHT"].add(new_line)
            new_line += 1
        else:
            in_hunk = False
    return files


def _inline_json(session: Session, row: PullRequestInlineComment, current_head_sha: str) -> dict:
    author = session.get(Principal, row.author_id)
    return {
        "id": row.id,
        "parent_id": row.parent_id,
        "author": service._collaboration_author(author),
        "head_sha": row.head_sha,
        "file_path": row.file_path,
        "line": row.line,
        "side": row.side,
        "body": row.body,
        "resolved": row.resolved,
        "is_current": row.head_sha.casefold() == current_head_sha.casefold(),
        "created_at": service._iso(row.created_at),
    }


def _pull_access(session: Session, principal: Principal, repository_id: str, number: int, *, write: bool):
    actor = service._active_collaboration_actor(session, principal, write=write)
    repository, project = service.require_repository(session, actor, repository_id, write=write)
    return actor, repository, project, service._live_pull(session, repository, number)


def list_inline_comments(session: Session, principal: Principal, repository_id: str, number: int) -> dict:
    actor, _, _, pull = _pull_access(session, principal, repository_id, number, write=False)
    rows = session.scalars(select(PullRequestInlineComment).where(
        PullRequestInlineComment.pull_request_id == pull.id,
    ).order_by(PullRequestInlineComment.created_at, PullRequestInlineComment.id)).all()
    return {"head_sha": pull.head_sha, "comments": [_inline_json(session, row, pull.head_sha) for row in rows]}


def pull_diff(session: Session, principal: Principal, repository_id: str, number: int) -> dict:
    _, repository, _, pull = _pull_access(session, principal, repository_id, number, write=False)
    diff = service._gitea().pull_diff(repository.owner, repository.name, pull.number)
    if not isinstance(diff, str) or len(diff.encode("utf-8")) > 5_000_000:
        raise DomainError(502, "gitea_invalid_diff", "Gitea returned an invalid pull request diff")
    current = service._gitea().pull(repository.owner, repository.name, pull.number)
    current_sha = ((current.get("head") or {}).get("sha") or current.get("head_sha")) if isinstance(current, dict) else None
    if not isinstance(current_sha, str) or current_sha.casefold() != pull.head_sha.casefold():
        raise DomainError(409, "stale_pull_request_head", "The pull request head changed while loading the diff")
    locations = parse_unified_diff(diff)
    return {
        "head_sha": pull.head_sha,
        "diff": diff,
        "files": [{"path": path, "left_lines": sorted(value["LEFT"]), "right_lines": sorted(value["RIGHT"])} for path, value in locations.items()],
    }


def _validate_location(repository: Repository, pull: PullRequest, payload: PullRequestInlineCommentCreate) -> None:
    if payload.head_sha.casefold() != pull.head_sha.casefold():
        raise DomainError(409, "stale_pull_request_head", "The pull request head changed; reload the diff before commenting")
    diff = service._gitea().pull_diff(repository.owner, repository.name, pull.number)
    if not isinstance(diff, str) or len(diff.encode("utf-8")) > 5_000_000:
        raise DomainError(502, "gitea_invalid_diff", "Gitea returned an invalid pull request diff")
    locations = parse_unified_diff(diff)
    if payload.line not in locations.get(payload.file_path, {}).get(payload.side, set()):
        raise DomainError(422, "inline_location_not_in_diff", "The selected file and line are not present on that side of the current pull request diff")
    current = service._gitea().pull(repository.owner, repository.name, pull.number)
    current_sha = ((current.get("head") or {}).get("sha") or current.get("head_sha")) if isinstance(current, dict) else None
    if not isinstance(current_sha, str) or current_sha.casefold() != pull.head_sha.casefold():
        raise DomainError(409, "stale_pull_request_head", "The pull request head changed while validating the diff")


def create_inline_comment(
    session: Session, principal: Principal, repository_id: str, number: int,
    route: str, key: str, payload: PullRequestInlineCommentCreate,
) -> dict:
    actor = service._active_collaboration_actor(session, principal, write=True)
    repository, project = service.require_repository(session, actor, repository_id, write=True)
    data = payload.model_dump(mode="json")
    cached = service._cached(session, actor, route, key, data)
    if cached is not None:
        return cached
    pull = service._live_pull(session, repository, number)
    _validate_location(repository, pull, payload)
    comment_id = new_id()

    def create():
        current_actor = service._active_collaboration_actor(session, actor, write=True)
        service.require_repository(session, current_actor, repository_id, write=True)
        row = PullRequestInlineComment(
            id=comment_id, pull_request_id=pull.id, parent_id=None, author_id=actor.id,
            head_sha=pull.head_sha, file_path=payload.file_path, line=payload.line,
            side=payload.side, body=payload.body, resolved=False, created_at=now_utc(),
        )
        session.add(row)
        session.flush()
        return _inline_json(session, row, pull.head_sha)

    return service._local_mutation(
        session, actor, route, key, data, "code.pull_request_inline_comment_added",
        "pull_request_inline_comment", comment_id, project.id, create,
        event_details={"repository_id": repository.id, "pull_number": pull.number},
    )


def reply_inline_comment(
    session: Session, principal: Principal, comment_id: str, route: str, key: str,
    payload: PullRequestInlineReplyCreate,
) -> dict:
    actor = service._active_collaboration_actor(session, principal, write=True)
    parent = session.get(PullRequestInlineComment, comment_id)
    if parent is None or parent.parent_id is not None:
        raise DomainError(404, "not_found", "Inline comment thread not found")
    pull = session.get(PullRequest, parent.pull_request_id)
    repository = session.get(Repository, pull.repository_id) if pull else None
    if pull is None or repository is None:
        raise DomainError(404, "not_found", "Inline comment thread not found")
    repository, project = service.require_repository(session, actor, repository.id, write=True)
    data = payload.model_dump(mode="json")
    data.update({"parent_id": parent.id})
    cached = service._cached(session, actor, route, key, data)
    if cached is not None:
        return cached
    row_id = new_id()

    def create():
        current_actor = service._active_collaboration_actor(session, actor, write=True)
        service.require_repository(session, current_actor, repository.id, write=True)
        row = PullRequestInlineComment(
            id=row_id, pull_request_id=pull.id, parent_id=parent.id, author_id=actor.id,
            head_sha=parent.head_sha, file_path=parent.file_path, line=parent.line,
            side=parent.side, body=payload.body, resolved=False, created_at=now_utc(),
        )
        session.add(row)
        session.flush()
        return _inline_json(session, row, pull.head_sha)

    return service._local_mutation(
        session, actor, route, key, data, "code.pull_request_inline_reply_added",
        "pull_request_inline_comment", row_id, project.id, create,
        event_details={"repository_id": repository.id, "pull_number": pull.number},
    )


def resolve_inline_comment(
    session: Session, principal: Principal, comment_id: str, route: str, key: str,
    payload: PullRequestInlineResolve,
) -> dict:
    actor = service._active_collaboration_actor(session, principal, write=True)
    row = session.get(PullRequestInlineComment, comment_id)
    if row is None or row.parent_id is not None:
        raise DomainError(404, "not_found", "Inline comment thread not found")
    pull = session.get(PullRequest, row.pull_request_id)
    repository = session.get(Repository, pull.repository_id) if pull else None
    if pull is None or repository is None:
        raise DomainError(404, "not_found", "Inline comment thread not found")
    repository, project = service.require_repository(session, actor, repository.id, write=True)
    data = payload.model_dump(mode="json")
    cached = service._cached(session, actor, route, key, data)
    if cached is not None:
        return cached

    def create():
        current_actor = service._active_collaboration_actor(session, actor, write=True)
        service.require_repository(session, current_actor, repository.id, write=True)
        row.resolved = payload.resolved
        session.flush()
        return _inline_json(session, row, pull.head_sha)

    return service._local_mutation(
        session, actor, route, key, data, "code.pull_request_inline_thread_resolved" if payload.resolved else "code.pull_request_inline_thread_reopened",
        "pull_request_inline_comment", row.id, project.id, create,
        event_details={"repository_id": repository.id, "pull_number": pull.number},
    )


def _supported_or_unavailable(operation):
    try:
        return operation(), None
    except DomainError as error:
        if error.status_code in {404, 405, 501} or error.code == "gitea_feature_unavailable":
            return None, {"available": False, "reason": "unsupported_by_gitea"}
        raise


def _rows(value, key: str) -> list[dict] | None:
    rows = value if isinstance(value, list) else value.get(key) if isinstance(value, dict) else None
    if not isinstance(rows, list) or any(not isinstance(item, dict) for item in rows):
        return None
    return rows


def _protection_for(client: GiteaClient, repository: Repository, branch: str) -> tuple[dict | None, dict | None]:
    payload, unavailable = _supported_or_unavailable(lambda: client.branch_protections(repository.owner, repository.name))
    if unavailable:
        return None, unavailable
    rows = _rows(payload, "branch_protections")
    if rows is None:
        raise DomainError(502, "gitea_invalid_response", "Gitea returned invalid branch protection data")
    protection = next((item for item in rows if item.get("branch_name") == branch), None)
    return protection, None


def get_branch_protection(session: Session, principal: Principal, repository_id: str, branch: str) -> dict:
    repository, _ = service.require_repository(session, principal, repository_id)
    if service._require_safe_ref(branch) != branch:
        raise DomainError(422, "invalid_branch", "Branch name is not a valid Git reference")
    config = load_gitea_config()
    if config is None:
        return {"available": False, "reason": "gitea_not_configured", "branch": branch, "protection": None}
    protection, unavailable = _protection_for(GiteaClient(config), repository, branch)
    if unavailable:
        return {**unavailable, "branch": branch, "protection": None}
    return {"available": True, "branch": branch, "protection": protection}


def update_branch_protection(
    session: Session, principal: Principal, repository_id: str, branch: str, route: str, key: str,
    payload,
) -> dict:
    repository, project = service.require_repository(session, principal, repository_id, manager=True)
    service._require_safe_ref(branch)
    request_data = {
        key: value
        for key, value in payload.model_dump(mode="json", exclude_unset=True).items()
        if value is not None
    }
    request_data["branch_name"] = branch
    cached = service._cached(session, principal, route, key, request_data)
    if cached is not None:
        return cached
    config = load_gitea_config()
    if config is None:
        raise DomainError(503, "gitea_not_configured", "Gitea is not configured")
    client = GiteaClient(config)
    client.branch(repository.owner, repository.name, branch)
    current, unavailable = _protection_for(client, repository, branch)
    if unavailable:
        raise DomainError(501, "gitea_feature_unavailable", "This Gitea version does not support branch protection management")
    upstream_data = dict(request_data)
    if current is None:
        upstream_data = {
            "required_approvals": 0,
            "enable_status_check": False,
            "status_check_contexts": [],
            "block_on_outdated_branch": False,
            "block_on_rejected_reviews": False,
            "dismiss_stale_approvals": False,
            "require_signed_commits": False,
            **request_data,
        }
    client.update_branch_protection(
        repository.owner, repository.name, branch, exists=current is not None, data=upstream_data,
    )
    actual, unavailable = _protection_for(client, repository, branch)
    if unavailable:
        raise DomainError(502, "gitea_invalid_response", "Gitea updated the policy but could not verify the result")
    if actual is None:
        raise DomainError(502, "gitea_invalid_response", "Gitea did not return the updated branch policy")
    result = {"available": True, "branch": branch, "protection": actual}

    def create():
        current_actor = service._active_collaboration_actor(session, principal, write=True)
        service.require_repository(session, current_actor, repository_id, manager=True)
        return result

    return service._local_mutation(
        session, principal, route, key, request_data, "code.branch_protection_updated",
        "repository", repository.id, project.id, create,
    )


def _safe_gitea_link(value, config) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        base = urlsplit(config.url)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or parsed.netloc != base.netloc or parsed.username or parsed.password:
        return None
    return value


def _actions_data(client: GiteaClient, repository: Repository, head_sha: str, config) -> dict:
    raw, unavailable = _supported_or_unavailable(lambda: client.actions_runs(repository.owner, repository.name, head_sha))
    if unavailable:
        return {**unavailable, "runs": []}
    runs = _rows(raw, "workflow_runs")
    if runs is None:
        return {"available": False, "reason": "invalid_upstream_response", "runs": []}
    result = []
    for run in runs:
        run_sha = run.get("head_sha")
        if not isinstance(run_sha, str) or run_sha.casefold() != head_sha.casefold():
            continue
        run_id = run.get("id")
        if not isinstance(run_id, int):
            continue
        jobs_raw, jobs_unavailable = _supported_or_unavailable(lambda: client.actions_jobs(repository.owner, repository.name, run_id))
        artifacts_raw, artifacts_unavailable = _supported_or_unavailable(lambda: client.actions_artifacts(repository.owner, repository.name, run_id))
        jobs = _rows(jobs_raw, "jobs") if not jobs_unavailable else None
        artifacts = _rows(artifacts_raw, "artifacts") if not artifacts_unavailable else None
        if jobs_unavailable or artifacts_unavailable or jobs is None or artifacts is None:
            return {"available": False, "reason": "actions_jobs_or_artifacts_unsupported", "runs": []}
        result.append({
            "id": run_id,
            "name": str(run.get("name") or run.get("display_title") or "")[:250],
            "head_sha": str(run_sha),
            "status": str(run.get("status") or "unknown"),
            "conclusion": run.get("conclusion"),
            "html_url": _safe_gitea_link(run.get("html_url") or run.get("url"), config),
            "created_at": run.get("created_at"),
            "jobs": [{
                "id": job.get("id"), "name": str(job.get("name") or "")[:250],
                "status": str(job.get("status") or "unknown"), "conclusion": job.get("conclusion"),
                "started_at": job.get("started_at"), "completed_at": job.get("completed_at"),
                "html_url": _safe_gitea_link(job.get("html_url") or job.get("url"), config),
            } for job in jobs],
            "artifacts": [{
                "id": artifact.get("id"), "name": str(artifact.get("name") or "")[:250],
                "size_in_bytes": artifact.get("size_in_bytes"), "expired": bool(artifact.get("expired")),
                "html_url": _safe_gitea_link(artifact.get("html_url") or artifact.get("url"), config),
            } for artifact in artifacts],
        })
    return {"available": True, "runs": result}


def pull_governance(session: Session, principal: Principal, repository_id: str, number: int) -> dict:
    repository, _ = service.require_repository(session, principal, repository_id)
    config = load_gitea_config()
    if config is None:
        raise DomainError(503, "gitea_not_configured", "Gitea is not configured")
    client = GiteaClient(config)
    remote = client.pull(repository.owner, repository.name, number)
    if not isinstance(remote, dict) or str(remote.get("number") or remote.get("id")) != str(number):
        raise DomainError(502, "gitea_invalid_pull_request", "Gitea returned an invalid pull request")
    pull = service._sync_pull(session, repository, remote)
    session.commit()
    head_sha = pull.head_sha

    raw_protection, protection_unavailable = _protection_for(client, repository, pull.base)
    protection = None if protection_unavailable else raw_protection
    reviews_raw, reviews_unavailable = _supported_or_unavailable(lambda: client.pull_reviews(repository.owner, repository.name, number))
    reviews = _rows(reviews_raw, "reviews") if not reviews_unavailable else None
    if reviews is None and not reviews_unavailable:
        reviews_unavailable = {"available": False, "reason": "invalid_upstream_response"}
    elif reviews is not None and len(reviews) >= 100:
        reviews = None
        reviews_unavailable = {"available": False, "reason": "upstream_pagination_limit_reached"}
    statuses_raw, statuses_unavailable = _supported_or_unavailable(lambda: client.statuses(repository.owner, repository.name, head_sha))
    statuses = _rows(statuses_raw, "statuses") if not statuses_unavailable else None
    if statuses is None and not statuses_unavailable:
        statuses_unavailable = {"available": False, "reason": "invalid_upstream_response"}
    elif statuses is not None and len(statuses) >= 100:
        statuses = None
        statuses_unavailable = {"available": False, "reason": "upstream_pagination_limit_reached"}

    latest_reviews = {}
    if reviews is not None:
        for review in reviews:
            review_sha = review.get("commit_id") or review.get("commit_sha") or ""
            user = review.get("user") or {}
            identity = user.get("login") or user.get("username") or user.get("id")
            if identity is not None:
                reviewed_at = str(review.get("submitted_at") or review.get("updated_at") or review.get("created_at") or "")
                prior = latest_reviews.get(identity)
                if prior is None or reviewed_at >= prior[0]:
                    latest_reviews[identity] = (
                        reviewed_at,
                        str(review.get("state") or "").casefold(),
                        str(review_sha),
                    )
    current_approvals = [
        identity for identity, (_, state, review_sha) in latest_reviews.items()
        if state == "approved" and review_sha.casefold() == head_sha.casefold()
    ]

    required_contexts = []
    required_approvals = 0
    if protection:
        required_approvals = int(protection.get("required_approvals") or 0)
        required_contexts = (protection.get("status_check_contexts") or []) if protection.get("enable_status_check") else []
        if not isinstance(required_contexts, list) or any(not isinstance(context, str) for context in required_contexts):
            raise DomainError(502, "gitea_invalid_response", "Gitea returned invalid required status contexts")
    statuses_by_context = {}
    upstream_checks = []
    if statuses is not None:
        for item in statuses:
            sha = item.get("sha") or head_sha
            if str(sha).casefold() == head_sha.casefold() and isinstance(item.get("context"), str):
                state = str(item.get("state") or "").casefold()
                created_at = str(item.get("created_at") or "")
                prior = statuses_by_context.get(item["context"])
                if prior is None or created_at >= prior[0]:
                    statuses_by_context[item["context"]] = (created_at, state)
                upstream_checks.append({
                    "context": item["context"], "state": state, "current_sha": head_sha,
                    "description": str(item.get("description") or "")[:500],
                    "target_url": _safe_gitea_link(item.get("target_url"), config),
                    "created_at": item.get("created_at"),
                })
    status_results = [{"context": context, "state": statuses_by_context.get(context, ("", "missing"))[1], "current_sha": head_sha} for context in required_contexts]
    mergeable = remote.get("mergeable") if isinstance(remote.get("mergeable"), bool) else None
    evidence_available = protection_unavailable is None and reviews_unavailable is None and statuses_unavailable is None
    blockers = []
    if mergeable is False:
        blockers.append("upstream_reports_conflicts")
    elif mergeable is None:
        blockers.append("mergeability_unknown")
    if len(current_approvals) < required_approvals:
        blockers.append("required_approvals_missing")
    if any(item["state"] != "success" for item in status_results):
        blockers.append("required_status_checks_incomplete")
    rejected_reviews = [
        identity for identity, (_, state, _) in latest_reviews.items()
        if state in {"request_changes", "changes_requested", "requested_changes", "rejected"}
    ]
    if protection and protection.get("block_on_rejected_reviews") and rejected_reviews:
        blockers.append("upstream_review_changes_requested")

    branch_sync = {"available": False, "behind_by": None}
    signed_commits = {"available": False, "all_signed": None, "unverified_count": None}
    if protection and protection.get("block_on_outdated_branch"):
        compare_fn = getattr(client, "compare", None)
        if callable(compare_fn):
            comparison, unavailable = _supported_or_unavailable(
                lambda: compare_fn(repository.owner, repository.name, pull.base, pull.head)
            )
            behind_by = comparison.get("behind_by") if isinstance(comparison, dict) else None
            if unavailable is None and isinstance(behind_by, int) and behind_by >= 0:
                branch_sync = {"available": True, "behind_by": behind_by}
                if behind_by > 0:
                    blockers.append("pull_branch_outdated")
            else:
                blockers.append("pull_branch_sync_unavailable")
        else:
            blockers.append("pull_branch_sync_unavailable")

    if protection and protection.get("require_signed_commits"):
        commits_fn = getattr(client, "pull_commits", None)
        if callable(commits_fn):
            commits_raw, unavailable = _supported_or_unavailable(
                lambda: commits_fn(repository.owner, repository.name, number)
            )
            commits = _rows(commits_raw, "commits")
            if commits is not None and len(commits) >= 100:
                commits = None
            if unavailable is None and commits is not None:
                verified = []
                signatures_complete = bool(commits)
                for commit_item in commits:
                    commit = commit_item.get("commit") if isinstance(commit_item.get("commit"), dict) else commit_item
                    verification = commit.get("verification") if isinstance(commit, dict) else None
                    if not isinstance(verification, dict) or not isinstance(verification.get("verified"), bool):
                        signatures_complete = False
                    else:
                        verified.append(verification["verified"])
                if signatures_complete:
                    signed_commits = {
                        "available": True,
                        "all_signed": all(verified),
                        "unverified_count": sum(1 for item in verified if not item),
                    }
                    if not all(verified):
                        blockers.append("pull_commits_unsigned")
                else:
                    blockers.append("pull_commit_signatures_unavailable")
            else:
                blockers.append("pull_commit_signatures_unavailable")
        else:
            blockers.append("pull_commit_signatures_unavailable")
    if not evidence_available:
        blockers.append("upstream_governance_unavailable")
    readiness_unknown = (
        not evidence_available
        or "pull_branch_sync_unavailable" in blockers
        or "pull_commit_signatures_unavailable" in blockers
    )
    return {
        "repository_id": repository.id,
        "pull_request_id": pull.id,
        "pull_number": pull.number,
        "head_sha": head_sha,
        "base_branch": pull.base,
        "upstream": {
            "mergeable": mergeable,
            "protection": {"available": True, "enabled": protection is not None, "policy": protection} if protection_unavailable is None else protection_unavailable,
            "reviews": {"available": reviews is not None, "reason": reviews_unavailable.get("reason") if reviews_unavailable else None, "current_approvals": current_approvals},
            "statuses": {"available": statuses is not None, "reason": statuses_unavailable.get("reason") if statuses_unavailable else None, "required": status_results, "checks": upstream_checks},
            "branch_sync": branch_sync,
            "commit_signatures": signed_commits,
        },
        "merge_readiness": {"ready": None if readiness_unknown else not blockers, "blockers": blockers, "verified_at_sha": head_sha},
        "actions": _actions_data(client, repository, head_sha, config),
        "deployments": deployments_for(repository, head_sha),
    }
