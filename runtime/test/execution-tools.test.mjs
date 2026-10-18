import assert from "node:assert/strict";
import { once } from "node:events";
import { createServer } from "node:http";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { createPlatformTools } from "../dist/platform-tools.js";
import { createMcpExtension, sanitizeMcpMetadata, sanitizeMcpOutput } from "../dist/mcp-tools.js";
import { createSandboxExtension } from "../dist/sandbox-tools.js";
import { RunStore } from "../dist/run-store.js";
import { RuntimeEngine } from "../dist/engine.js";
import { loadConfig } from "../dist/config.js";

function config(dataDir, apiUrl = "http://127.0.0.1:8000") {
  return loadConfig({
    NODE_ENV: "test",
    ORDIVANT_RUNTIME_MODE: "demo",
    ORDIVANT_RUNTIME_TOKEN: "test-runtime-token",
    ORDIVANT_DATA_DIR: dataDir,
    ORDIVANT_API_URL: apiUrl,
  });
}

async function listen(server) {
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  return `http://127.0.0.1:${server.address().port}`;
}

async function close(server) {
  if (!server.listening) return;
  server.close();
  await once(server, "close");
}

function sandboxConfig(dataDir) {
  return {
    ...config(dataDir),
    sandboxUrl: "http://127.0.0.1:8040",
    sandboxToken: "test-sandbox-service-token",
  };
}

async function waitFor(predicate, timeoutMs = 3_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = predicate();
    if (value) return value;
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  throw new Error("timed out waiting for runtime state");
}

test("queued cooperative pause opens one persisted Pi request after resume", async () => {
  const dataDir = mkdtempSync(join(tmpdir(), "ordivant-pause-"));
  const engine = new RuntimeEngine(config(dataDir));
  const requestId = "pause-resume-run-1";
  try {
    const result = await engine.enqueue({
      request_id: requestId,
      task_id: "task-1",
      agent_id: "agent-1",
      prompt: "Complete the deterministic smoke task.",
      execution_config: { instructions: "", tool_connection_ids: [], sandbox_profile_id: null, limits: { max_turns: 2, timeout_seconds: 30 } },
    }, { project_id: "project-1", desired_action: "pause", control_revision: 1 });
    assert.equal(result.status, "queued");
    const paused = await waitFor(() => {
      const run = engine.store.get(requestId);
      return run?.status === "paused" ? run : undefined;
    });
    assert.equal(paused.submission_id, null);
    assert.equal(paused.control_revision, 1);

    await engine.applyControl(requestId, "resume", 2);
    const completed = await engine.waitFor(requestId);
    assert.equal(completed.status, "done");
    assert.ok(completed.submission_id);
    assert.equal(completed.control_revision, 2);
    assert.deepEqual(engine.store.events(requestId).filter((event) => event.kind === "status").map((event) => event.data.status), ["queued", "paused", "running", "done"]);
  } finally {
    await engine.close();
    rmSync(dataDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 50 });
  }
});

test("Pi Durable demo executes a real platform tool and records tool events and receipt", async () => {
  const dataDir = mkdtempSync(join(tmpdir(), "ordivant-demo-tool-events-"));
  const seen = [];
  const platformServer = createServer((request, response) => {
    const path = new URL(request.url, "http://127.0.0.1").pathname;
    seen.push({ method: request.method, path, authorization: request.headers.authorization });
    const status = request.method === "GET" && path === "/api/tasks/task-1/context" &&
      request.headers.authorization === "Bearer scoped-demo-agent-token" ? 200 : 404;
    const payload = status === 200
      ? { task: { id: "task-1", title: "Tool event smoke task" }, executions: [], artifacts: [], messages: [], events: [], dependencies: [] }
      : { detail: { message: "Not found" } };
    const text = JSON.stringify(payload);
    response.writeHead(status, { "content-type": "application/json", "content-length": Buffer.byteLength(text) });
    response.end(text);
  });
  let engine;
  try {
    const apiUrl = await listen(platformServer);
    engine = new RuntimeEngine(config(dataDir, apiUrl));
    const requestId = "demo-tool-events-1";
    await engine.enqueue({
      request_id: requestId,
      task_id: "task-1",
      agent_id: "agent-1",
      prompt: "Use get_task_context once, then summarize the task title.",
      execution_config: { instructions: "", tool_connection_ids: [], sandbox_profile_id: null, limits: { max_turns: 2, timeout_seconds: 30 } },
    }, {
      project_id: "project-1",
      agent_credential: { id: "agent-1", token: "scoped-demo-agent-token" },
    });

    const completed = await engine.waitFor(requestId);
    assert.equal(completed.status, "done");
    assert.deepEqual(seen, [{
      method: "GET",
      path: "/api/tasks/task-1/context",
      authorization: "Bearer scoped-demo-agent-token",
    }]);
    const events = engine.store.events(requestId);
    const toolStart = events.find((event) => event.kind === "tool_start");
    const toolEnd = events.find((event) => event.kind === "tool_end");
    assert.equal(toolStart?.data.tool_name, "get_task_context");
    assert.equal(toolStart?.data.tool_call_id, toolEnd?.data.tool_call_id);
    assert.equal(toolEnd?.data.completed, true);
    assert.deepEqual(completed.receipt.tools, [{ name: "get_task_context", calls: 1 }]);
  } finally {
    await engine?.close();
    await close(platformServer);
    rmSync(dataDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 50 });
  }
});

test("platform tool waits for the lease gate before making its scoped request", async () => {
  const order = [];
  let leaseValid = true;
  const credential = { id: "agent-1", token: "scoped-token" };
  const activeRun = {
    request_id: "run-1",
    task_id: "task-1",
    agent_id: "agent-1",
    project_id: "project-1",
    agent_credential: credential,
    beforeToolOperation: async () => {
      order.push("pause-gate");
      if (!leaseValid) throw new Error("lease was fenced");
      order.push("lease-check");
    },
  };
  const client = {
    agentGet: async (_agentId, _path, receivedCredential) => {
      assert.equal(receivedCredential, credential);
      order.push("platform-request");
      return { task: "current" };
    },
  };
  const extension = createPlatformTools(client, (conversationId) => conversationId === "conversation-1" ? activeRun : undefined);
  const tool = extension.tools.find((candidate) => candidate.name === "get_task_context");
  assert.ok(tool);
  const api = { conversationId: "conversation-1", taskId: "task-1" };

  const result = await tool.execute({}, api, {});
  assert.deepEqual(order, ["pause-gate", "lease-check", "platform-request"]);
  assert.match(result.output[0].text, /current/);

  order.length = 0;
  leaseValid = false;
  await assert.rejects(() => tool.execute({}, api, {}), /lease was fenced/);
  assert.deepEqual(order, ["pause-gate"]);
});

test("lease-bound platform writes wait for queued renewal and capture the rotated token", async () => {
  let queue = Promise.resolve();
  const withLeaseOperation = (operation) => {
    const current = queue.then(operation);
    queue = current.then(() => undefined, () => undefined);
    return current;
  };
  let backendToken = "lease-before-renew";
  let renewalInFlight = false;
  let signalRenewalStarted;
  let finishRenewal;
  let signalGateEntered;
  let finishGate;
  const renewalStarted = new Promise((resolve) => { signalRenewalStarted = resolve; });
  const renewalHold = new Promise((resolve) => { finishRenewal = resolve; });
  const gateEntered = new Promise((resolve) => { signalGateEntered = resolve; });
  const gateHold = new Promise((resolve) => { finishGate = resolve; });
  const requests = [];
  const lease = { execution_id: "execution-1", lease_token: backendToken, lease_seconds: 30 };
  const credential = { id: "agent-1", token: "scoped-token" };
  const client = {
    agentPost: async (_agentId, path, body, _key, receivedCredential) => {
      assert.equal(receivedCredential, credential);
      assert.equal(body.lease_token, backendToken);
      if (path.endsWith("/renew")) {
        renewalInFlight = true;
        requests.push({ path, token: body.lease_token });
        signalRenewalStarted();
        await renewalHold;
        backendToken = "lease-after-renew";
        lease.lease_token = backendToken;
        renewalInFlight = false;
        return { execution: { id: lease.execution_id }, lease_token: backendToken };
      }
      assert.equal(path, "/api/tasks/task-1/progress");
      assert.equal(renewalInFlight, false, "platform write must wait for the in-flight lease renewal");
      requests.push({ path, token: body.lease_token });
      return { progress: body.progress };
    },
  };
  const activeRun = {
    request_id: "run-lease-queue-1",
    task_id: "task-1",
    agent_id: "agent-1",
    project_id: "project-1",
    lease,
    agent_credential: credential,
    withLeaseOperation,
    beforeToolOperation: async () => {
      signalGateEntered();
      await gateHold;
    },
  };
  const extension = createPlatformTools(client, (conversationId) => conversationId === "conversation-1" ? activeRun : undefined);
  const tool = extension.tools.find((candidate) => candidate.name === "report_progress");
  assert.ok(tool);
  const api = { conversationId: "conversation-1", taskId: "task-1" };
  const toolOutcome = tool.execute({ progress: 15, summary: "Lease race check" }, api, {})
    .then((value) => ({ value }), (error) => ({ error }));

  await gateEntered;
  const renewal = withLeaseOperation(() => client.agentPost(
    "agent-1",
    "/api/tasks/task-1/renew",
    { execution_id: lease.execution_id, lease_token: lease.lease_token, lease_seconds: 30 },
    "renew-key",
    credential,
  ));
  await renewalStarted;
  finishGate();
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(requests, [{ path: "/api/tasks/task-1/renew", token: "lease-before-renew" }]);

  finishRenewal();
  const [renewalResult, toolResult] = await Promise.all([renewal, toolOutcome]);
  assert.equal(renewalResult.lease_token, "lease-after-renew");
  assert.equal(toolResult.error, undefined);
  assert.deepEqual(requests, [
    { path: "/api/tasks/task-1/renew", token: "lease-before-renew" },
    { path: "/api/tasks/task-1/progress", token: "lease-after-renew" },
  ]);
  assert.match(toolResult.value.output[0].text, /"progress":15/);
});

test("a fenced execution aborts safely before creating a Pi submission", async () => {
  const dataDir = mkdtempSync(join(tmpdir(), "ordivant-fence-"));
  const engine = new RuntimeEngine(config(dataDir));
  let leaseChecks = 0;
  const requestId = "fenced-run-1";
  try {
    await engine.enqueue({
      request_id: requestId,
      task_id: "task-1",
      agent_id: "agent-1",
      execution_id: "execution-1",
      prompt: "This run must not submit after its lease is fenced.",
    }, {
      project_id: "project-1",
      assertLease: async () => {
        leaseChecks += 1;
        throw new Error("lease was fenced");
      },
    });

    const completed = await engine.waitFor(requestId);
    assert.equal(completed.status, "failed");
    assert.equal(completed.submission_id, null);
    assert.match(completed.error, /Execution lease was lost/);
    assert.equal(leaseChecks, 1);
  } finally {
    await engine.close();
    rmSync(dataDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 50 });
  }
});

test("recovery fails closed when a paused sandbox capability was lost", async () => {
  const dataDir = mkdtempSync(join(tmpdir(), "ordivant-sandbox-recovery-"));
  const engine = new RuntimeEngine(sandboxConfig(dataDir));
  const requestId = "sandbox-recovery-run-1";
  try {
    await engine.enqueue({
      request_id: requestId,
      task_id: "task-1",
      agent_id: "agent-1",
      execution_id: "execution-1",
      prompt: "Resume only if the existing workspace capability is available.",
      sandbox_profile: {
        id: "profile-1",
        project_id: "project-1",
        name: "test",
        limits: { timeout_seconds: 10, memory_mb: 64, cpu_count: 0.5, pids_limit: 16, output_bytes: 1024, workspace_mb: 1 },
      },
    }, { project_id: "project-1", desired_action: "pause", control_revision: 1 });

    await waitFor(() => engine.store.get(requestId)?.status === "paused");
    engine.store.setSandbox(requestId, { run_id: requestId, status: "ready", workspace_available: true });
    await engine.applyControl(requestId, "resume", 2);

    const completed = await engine.waitFor(requestId);
    assert.equal(completed.status, "failed");
    assert.equal(completed.submission_id, null);
    assert.deepEqual(completed.sandbox, { run_id: requestId, status: "lost", workspace_available: false });
    assert.match(completed.error, /Sandbox workspace was lost during runtime recovery/);
  } finally {
    await engine.close();
    rmSync(dataDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 50 });
  }
});

test("sandbox cleanup reports unconfirmed failure without changing the run result", async () => {
  const capability = "sandbox-capability-never-persist-this-value-123456";
  const privateFailureDetail = "executor echoed private cleanup detail";

  for (const deleteFails of [true, false]) {
    const dataDir = mkdtempSync(join(tmpdir(), "ordivant-sandbox-cleanup-"));
    const requests = [];
    const requestId = deleteFails ? "sandbox-cleanup-fails" : "sandbox-cleanup-succeeds";
    const profile = {
      id: "profile-1",
      project_id: "project-1",
      name: "cleanup fixture",
      limits: { timeout_seconds: 10, memory_mb: 64, cpu_count: 0.5, pids_limit: 16, output_bytes: 1024, workspace_mb: 1 },
    };
    const server = createServer(async (request, response) => {
      for await (const _chunk of request) {}
      requests.push({ method: request.method, path: request.url });
      if (request.method === "POST" && request.url === "/sandboxes") {
        const body = JSON.stringify({ run_id: requestId, status: "ready", token: capability });
        response.writeHead(201, { "content-type": "application/json", "content-length": Buffer.byteLength(body) });
        response.end(body);
      } else if (request.method === "DELETE" && request.url === `/sandboxes/${requestId}` && deleteFails) {
        const body = JSON.stringify({ detail: privateFailureDetail });
        response.writeHead(503, { "content-type": "application/json", "content-length": Buffer.byteLength(body) });
        response.end(body);
      } else if (request.method === "DELETE" && request.url === `/sandboxes/${requestId}`) {
        response.writeHead(204);
        response.end();
      } else {
        response.writeHead(404, { "content-type": "application/json" });
        response.end(JSON.stringify({ detail: "Not found" }));
      }
    });
    let engine;
    try {
      const apiUrl = await listen(server);
      engine = new RuntimeEngine({
        ...sandboxConfig(dataDir),
        sandboxUrl: apiUrl,
      });
      await engine.enqueue({
        request_id: requestId,
        task_id: "task-1",
        agent_id: "agent-1",
        prompt: "Complete this deterministic smoke task.",
        execution_config: { instructions: "", tool_connection_ids: [], sandbox_profile_id: "profile-1", limits: { max_turns: 2, timeout_seconds: 30 } },
        sandbox_profile: profile,
      }, { project_id: "project-1", sandbox_profile: profile });

      const completed = await engine.waitFor(requestId);
      assert.equal(completed.status, "done", "sandbox cleanup outcome must not rewrite the completed Pi run");
      assert.deepEqual(requests, [
        { method: "POST", path: "/sandboxes" },
        { method: "DELETE", path: `/sandboxes/${requestId}` },
      ]);
      if (deleteFails) {
        assert.deepEqual(completed.sandbox, { run_id: requestId, status: "failed", workspace_available: false });
        const cleanupEvent = engine.store.events(requestId).find((event) => event.data.kind === "sandbox_cleanup_unconfirmed");
        assert.equal(cleanupEvent?.kind, "error");
        assert.equal(cleanupEvent?.data.message, "沙箱清理尚未確認，請由操作者檢查執行器。");
        const persistedEvidence = JSON.stringify({ sandbox: completed.sandbox, events: engine.store.events(requestId) });
        assert.equal(persistedEvidence.includes(capability), false);
        assert.equal(persistedEvidence.includes(privateFailureDetail), false);
      } else {
        assert.deepEqual(completed.sandbox, { run_id: requestId, status: "stopped", workspace_available: false });
        assert.equal(engine.store.events(requestId).some((event) => event.data.kind === "sandbox_cleanup_unconfirmed"), false);
      }
    } finally {
      await engine?.close();
      await close(server);
      rmSync(dataDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 50 });
    }
  }
});

test("RunStore preserves pending sync and bounded sanitized events across restart", () => {
  const dataDir = mkdtempSync(join(tmpdir(), "ordivant-run-store-"));
  const path = join(dataDir, "runs.sqlite");
  const input = { request_id: "run-store-1", task_id: "task-1", agent_id: "agent-1", prompt: "prompt" };
  try {
    let store = new RunStore(path);
    store.reserve(input, "1");
    store.appendEvent(input.request_id, "tool_start", { tool_name: "sandbox_execute", authorization: "must-not-persist", text: "Bearer sensitive-token" });
    const pending = store.prepareSync(input.request_id, { status: "running", events: store.unsyncedEvents(input.request_id) }, 2);
    assert.equal(pending.sequence, 1);
    store.close();

    store = new RunStore(path);
    const replayed = store.prepareSync(input.request_id, { status: "different" }, 0);
    assert.deepEqual(replayed, pending);
    const event = store.events(input.request_id).find((item) => item.kind === "tool_start");
    assert.equal(event.data.authorization, undefined);
    assert.equal(event.data.text, "Bearer [redacted]");
    store.completeSync(input.request_id, replayed.sequence, replayed.event_sequence);
    assert.equal(store.get(input.request_id).synced_sequence, replayed.event_sequence);
    store.close();
  } finally {
    rmSync(dataDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 50 });
  }
});

test("sandbox tool success and binding errors expose model-visible Pi output", async () => {
  let bound = true;
  let reads = 0;
  const run = {
    request_id: "sandbox-output-run", task_id: "task-1", agent_id: "agent-1",
    sandbox_capability: "synthetic-sandbox-capability",
    sandbox_profile: { limits: {} },
  };
  const client = { readFile: async () => { reads++; return { path: "note.md", content: "sandbox output evidence" }; } };
  const extension = createSandboxExtension(client, () => bound ? run : undefined);
  const tool = extension.tools.find(item => item.name === "sandbox_read_file");
  const api = { conversationId: "conversation-1" };
  const result = await tool.execute({ path: "note.md" }, api, {});
  assert.equal(JSON.parse(result.output[0].text).content, "sandbox output evidence");
  assert.equal(result.isError, undefined);
  bound = false;
  const denied = await tool.execute({ path: "note.md" }, api, {});
  assert.equal(denied.isError, true);
  assert.match(denied.output[0].text, /No active sandbox/);
  assert.equal(reads, 1);
});

test("MCP calls preserve model-visible errors, redaction and run binding with Pi", async () => {
  const credential = "synthetic-mcp-output-credential";
  let calls = 0;
  const server = createServer(async (request, response) => {
    if (request.method !== "POST") { response.writeHead(405).end(); return; }
    assert.equal(request.headers.authorization, `Bearer ${credential}`);
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    const message = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    if (message.id === undefined) { response.writeHead(202).end(); return; }
    let result;
    if (message.method === "initialize") {
      result = { protocolVersion: message.params.protocolVersion, capabilities: { tools: {} }, serverInfo: { name: "output-fixture", version: "1.0.0" } };
    } else if (message.method === "tools/list") {
      result = { tools: [{ name: "echo", inputSchema: { type: "object", properties: {} } }] };
    } else {
      assert.equal(message.method, "tools/call");
      assert.equal(message.params.name, "echo");
      calls++;
      result = { isError: true, content: [{ type: "text", text: `upstream diagnostic ${credential}` }] };
    }
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({ jsonrpc: "2.0", id: message.id, result }));
  });
  try {
    const endpoint = await listen(server);
    const connection = { id: "output-fixture", name: "Output fixture", endpoint, auth_token: credential, allowed_tools: ["echo"] };
    let bound = true;
    const extension = await createMcpExtension("output-run", [connection], {
      ...config(tmpdir()), toolAllowedHosts: ["127.0.0.1"], toolHttpHosts: ["127.0.0.1"], toolPrivateHosts: ["127.0.0.1"],
    }, () => bound ? { tool_connections: [connection] } : undefined);
    const tool = extension.tools[0];
    const result = await tool.execute({}, { conversationId: "conversation-1" }, {});
    assert.equal(result.isError, true);
    assert.match(result.output[0].text, /upstream diagnostic/);
    assert.match(result.output[0].text, /\[redacted\]/);
    assert.equal(result.output[0].text.includes(credential), false);
    bound = false;
    const denied = await tool.execute({}, { conversationId: "conversation-1" }, {});
    assert.equal(denied.isError, true);
    assert.match(denied.output[0].text, /not bound/);
    assert.equal(calls, 1);
  } finally { await close(server); }
});

test("MCP list metadata and tool output redact the exact configured bearer token", () => {
  const credential = "fixture-remote-bearer-credential-value";
  const metadata = sanitizeMcpMetadata({
    description: `The service echoed ${credential}`,
    inputSchema: { properties: { note: { description: `Echo: ${credential}`, default: credential } } },
  }, credential);
  const output = sanitizeMcpOutput({ content: [{ type: "text", text: `remote error echoed ${credential}` }] }, credential);
  assert.equal(JSON.stringify(metadata).includes(credential), false);
  assert.equal(output.includes(credential), false);
  assert.match(output, /\[redacted\]/);
});
