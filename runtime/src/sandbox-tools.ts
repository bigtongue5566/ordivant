import { Type } from "@earendil-works/pi-ai";
import { defineExtension, defineTool } from "@earendil-works/pi-durable";
import type { ToolExecutionResult } from "@earendil-works/pi-durable";
import type { RunExecutionContext } from "./types.js";
import { SandboxClient } from "./sandbox-client.js";

type ActiveRunLookup = (conversationId: string) => (RunExecutionContext & {
  request_id: string;
  task_id: string;
  agent_id: string;
}) | undefined;

function resultText(value: unknown, isError = false): ToolExecutionResult {
  return { output: [{ type: "text", text: JSON.stringify(value) }], ...(isError ? { isError: true } : {}) };
}

async function runContext(api: { conversationId: unknown }, activeRun: ActiveRunLookup) {
  const run = activeRun(String(api.conversationId));
  if (!run?.sandbox_profile || !run.sandbox_capability) return undefined;
  await run.beforeToolOperation?.();
  return run as typeof run & { sandbox_profile: NonNullable<typeof run.sandbox_profile>; sandbox_capability: string };
}

export function createSandboxExtension(client: SandboxClient, activeRun: ActiveRunLookup) {
  const writeFile = defineTool({
    name: "sandbox_write_file",
    description: "Write UTF-8 content to a relative file in this run's isolated workspace.",
    parameters: Type.Object({ path: Type.String({ minLength: 1, maxLength: 4096 }), content: Type.String({ maxLength: 16_777_216 }) }),
    replay: "unsafe",
    outputLimits: { maxBytes: 64_000, retain: "head" },
    execute: async (args, api) => {
      const run = await runContext(api, activeRun);
      if (!run) return resultText({ error: "No active sandbox is bound to this run." }, true);
      try {
        const result = await client.writeFile(run.request_id, run.sandbox_capability, run.sandbox_profile.limits, args.path, args.content);
        run.recordSandboxEvidence?.({ operation: "write_file", ...result });
        return resultText(result);
      } catch {
        run.recordSandboxEvidence?.({ operation: "write_file", path: args.path, exit_code: 1, stderr: "Sandbox file write failed." });
        return resultText({ error: "Sandbox file write failed." }, true);
      }
    },
  });

  const readFile = defineTool({
    name: "sandbox_read_file",
    description: "Read a bounded UTF-8 file from this run's isolated workspace.",
    parameters: Type.Object({ path: Type.String({ minLength: 1, maxLength: 4096 }) }),
    replay: "safe",
    outputLimits: { maxBytes: 64_000, retain: "head" },
    execute: async (args, api) => {
      const run = await runContext(api, activeRun);
      if (!run) return resultText({ error: "No active sandbox is bound to this run." }, true);
      try {
        const result = await client.readFile(run.request_id, run.sandbox_capability, run.sandbox_profile.limits, args.path);
        run.recordSandboxEvidence?.({ operation: "read_file", ...result });
        return resultText(result);
      } catch {
        run.recordSandboxEvidence?.({ operation: "read_file", path: args.path, exit_code: 1, stderr: "Sandbox file read failed." });
        return resultText({ error: "Sandbox file read failed." }, true);
      }
    },
  });

  const listFiles = defineTool({
    name: "sandbox_list_files",
    description: "List files and directories in this run's isolated workspace.",
    parameters: Type.Object({ path: Type.Optional(Type.String({ maxLength: 4096 })) }),
    replay: "safe",
    outputLimits: { maxBytes: 64_000, retain: "head" },
    execute: async (args, api) => {
      const run = await runContext(api, activeRun);
      if (!run) return resultText({ error: "No active sandbox is bound to this run." }, true);
      try {
        const result = await client.listFiles(run.request_id, run.sandbox_capability, run.sandbox_profile.limits, args.path ?? ".");
        run.recordSandboxEvidence?.({ operation: "list_files", ...(result as Record<string, unknown>) });
        return resultText(result);
      } catch {
        run.recordSandboxEvidence?.({ operation: "list_files", path: args.path ?? ".", exit_code: 1, stderr: "Sandbox file listing failed." });
        return resultText({ error: "Sandbox file listing failed." }, true);
      }
    },
  });

  const execute = defineTool({
    name: "sandbox_execute",
    description: "Execute a bounded argv command inside this run's isolated, network-disabled workspace.",
    parameters: Type.Object({
      command: Type.Array(Type.String({ minLength: 1, maxLength: 32_768 }), { minItems: 1, maxItems: 128 }),
      timeout_seconds: Type.Optional(Type.Integer({ minimum: 1, maximum: 120 })),
    }),
    replay: "unsafe",
    outputLimits: { maxBytes: 64_000, retain: "head" },
    execute: async (args, api) => {
      const run = await runContext(api, activeRun);
      if (!run) return resultText({ error: "No active sandbox is bound to this run." }, true);
      if (args.command.some((part) => part.includes("\0")) || args.command.reduce((sum, part) => sum + Buffer.byteLength(part), 0) > 256 * 1024) {
        return resultText({ error: "Command arguments exceed the runtime limit." }, true);
      }
      try {
        const result = await client.execute(run.request_id, run.sandbox_capability, run.sandbox_profile.limits, args.command, args.timeout_seconds);
        const exitCode = typeof result.exit_code === "number" ? result.exit_code : 1;
        const timedOut = result.timed_out === true;
        run.recordSandboxEvidence?.({ operation: "execute", ...result });
        return resultText(result, timedOut || exitCode !== 0);
      } catch {
        run.recordSandboxEvidence?.({ operation: "execute", exit_code: 1, stderr: "Sandbox command request failed." });
        return resultText({ error: "Sandbox command request failed or timed out." }, true);
      }
    },
  });

  return defineExtension({ name: "ordivant-sandbox-tools", tools: [writeFile, readFile, listFiles, execute] });
}
