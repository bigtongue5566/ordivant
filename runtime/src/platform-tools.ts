import { Type } from "@earendil-works/pi-ai";
import { defineExtension, defineTool } from "@earendil-works/pi-durable";
import type { ToolExecutionApi, ToolExecutionResult } from "@earendil-works/pi-durable";
import { PlatformClient } from "./platform-client.js";
import type { RunExecutionContext } from "./types.js";

export type ActiveRunLookup = (conversationId: string) => (RunExecutionContext & {
  request_id: string;
  task_id: string;
  agent_id: string;
}) | undefined;

function jsonToolResult(value: unknown): ToolExecutionResult {
  return { output: [{ type: "text", text: JSON.stringify(value) }] };
}

export function createPlatformTools(client: PlatformClient, activeRun: ActiveRunLookup) {
  const withRun = (api: ToolExecutionApi) => {
    const run = activeRun(String(api.conversationId));
    if (!run) throw new Error("No active platform lease is associated with this conversation");
    return run;
  };
  const credentialFor = (run: ReturnType<typeof withRun>) => {
    if (!run.agent_credential) throw new Error("No scoped Ordivant credential is associated with this run");
    return run.agent_credential;
  };
  const withLease = (api: ToolExecutionApi) => {
    const run = withRun(api);
    if (!run.lease) throw new Error("This run has no active task lease");
    return run as typeof run & { lease: NonNullable<typeof run.lease> };
  };
  const beforePlatformOperation = async (run: ReturnType<typeof withRun>) => {
    await run.beforeToolOperation?.();
  };
  const projectId = async (run: ReturnType<typeof withRun>): Promise<string> => {
    if (run.project_id) return run.project_id;
    const task = await client.agentGet<{ project_id?: string }>(
      run.agent_id,
      `/api/tasks/${encodeURIComponent(run.task_id)}`,
      credentialFor(run),
    );
    if (!task.project_id) throw new Error("The current task has no project scope");
    run.project_id = task.project_id;
    return task.project_id;
  };
  const mutationKey = (run: { request_id: string }, api: ToolExecutionApi) =>
    `pi-tool:${run.request_id}:${api.taskId}`;

  const getTaskContext = defineTool({
    name: "get_task_context",
    description: "Read the current task, evidence, execution history, messages, and audit events.",
    parameters: Type.Object({}),
    replay: "safe",
    execute: async (_args, api) => {
      const run = withRun(api);
      await beforePlatformOperation(run);
      const result = await client.agentGet<unknown>(
        run.agent_id,
        `/api/tasks/${encodeURIComponent(run.task_id)}/context`,
        credentialFor(run),
      );
      return jsonToolResult(result);
    },
  });

  const findReadyTasks = defineTool({
    name: "find_ready_tasks",
    description: "Find ready tasks visible to this agent in the current project.",
    parameters: Type.Object({}),
    replay: "safe",
    execute: async (_args, api) => {
      const run = withRun(api);
      await beforePlatformOperation(run);
      const query = new URLSearchParams({ ready_only: "true" });
      if (run.project_id) query.set("project_id", run.project_id);
      const result = await client.agentGet<unknown>(run.agent_id, `/api/tasks?${query.toString()}`, credentialFor(run));
      return jsonToolResult(result);
    },
  });

  const reportProgress = defineTool({
    name: "report_progress",
    description: "Report evidence-based progress for the currently leased task.",
    parameters: Type.Object({
      progress: Type.Number({ minimum: 0, maximum: 89 }),
      summary: Type.Optional(Type.String({ maxLength: 4000 })),
    }),
    replay: "safe",
    execute: async (args, api) => {
      const run = withRun(api);
      await beforePlatformOperation(run);
      const write = async () => {
        const leasedRun = withLease(api);
        const lease = leasedRun.lease;
        const executionId = lease.execution_id;
        const leaseToken = lease.lease_token;
        return client.agentPost<unknown>(leasedRun.agent_id,
          `/api/tasks/${encodeURIComponent(leasedRun.task_id)}/progress`,
          {
            execution_id: executionId,
            lease_token: leaseToken,
            progress: args.progress,
            ...(args.summary === undefined ? {} : { summary: args.summary }),
          },
          mutationKey(leasedRun, api),
          credentialFor(leasedRun),
        );
      };
      const result = run.withLeaseOperation
        ? await run.withLeaseOperation(write)
        : await write();
      return jsonToolResult(result);
    },
  });

  const sendMessage = defineTool({
    name: "send_message",
    description: "Send a project-scoped question, reply, help request, decision, or handoff message.",
    parameters: Type.Object({
      recipient_id: Type.Optional(Type.String({ minLength: 1 })),
      kind: Type.Union([
        Type.Literal("question"), Type.Literal("reply"), Type.Literal("help_request"),
        Type.Literal("decision"), Type.Literal("handoff"),
      ]),
      body: Type.String({ minLength: 1, maxLength: 12000 }),
      reply_to_id: Type.Optional(Type.String({ minLength: 1 })),
    }),
    replay: "safe",
    execute: async (args, api) => {
      const run = withRun(api);
      await beforePlatformOperation(run);
      const result = await client.agentPost<unknown>(run.agent_id, "/api/messages", {
        project_id: await projectId(run),
        task_id: run.task_id,
        ...(args.recipient_id === undefined ? {} : { recipient_id: args.recipient_id }),
        kind: args.kind,
        body: args.body,
        ...(args.reply_to_id === undefined ? {} : { reply_to_id: args.reply_to_id }),
      }, mutationKey(run, api), credentialFor(run));
      return jsonToolResult(result);
    },
  });

  const delegateTask = defineTool({
    name: "delegate_task",
    description: "Create a scoped child task assigned to another authorized agent.",
    parameters: Type.Object({
      agent_id: Type.String({ minLength: 1 }),
      title: Type.String({ minLength: 1, maxLength: 300 }),
      goal: Type.String({ minLength: 1, maxLength: 4000 }),
      description: Type.Optional(Type.String({ maxLength: 8000 })),
      inputs: Type.Optional(Type.String({ maxLength: 8000 })),
      scope: Type.Optional(Type.String({ maxLength: 8000 })),
      constraints: Type.Optional(Type.String({ maxLength: 8000 })),
      acceptance_criteria: Type.Array(Type.String({ minLength: 1, maxLength: 1000 }), { minItems: 1, maxItems: 20 }),
      priority: Type.Optional(Type.Union([
        Type.Literal("urgent"), Type.Literal("high"), Type.Literal("medium"), Type.Literal("low"),
      ])),
      budget_usd: Type.Optional(Type.Number({ minimum: 0 })),
    }),
    replay: "safe",
    execute: async (args, api) => {
      const run = withRun(api);
      await beforePlatformOperation(run);
      const result = await client.agentPost<unknown>(run.agent_id,
        `/api/tasks/${encodeURIComponent(run.task_id)}/delegate`,
        args,
        mutationKey(run, api),
        credentialFor(run),
      );
      return jsonToolResult(result);
    },
  });

  return defineExtension({
    name: "ordivant-platform",
    tools: [getTaskContext, findReadyTasks, reportProgress, sendMessage, delegateTask],
  });
}
