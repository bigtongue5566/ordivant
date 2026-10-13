import { createHash } from "node:crypto";
import { Client, StreamableHTTPClientTransport, type Tool as McpTool } from "@modelcontextprotocol/client";
import { Type } from "@earendil-works/pi-ai";
import { defineExtension, defineTool } from "@earendil-works/pi-durable";
import type { ToolExecutionApi, ToolRegistration } from "@earendil-works/pi-durable";
import type { RunExecutionContext, RuntimeConfig, ToolConnectionCredential } from "./types.js";
import { assertToolEndpointAllowed, guardedFetch } from "./tool-policy.js";

type RunLookup = (conversationId: string) => (RunExecutionContext & {
  request_id: string;
  task_id: string;
  agent_id: string;
  tool_connections?: ToolConnectionCredential[];
}) | undefined;

function toolName(connectionId: string, name: string, index: number): string {
  const namespace = connectionId.replace(/[^A-Za-z0-9]/g, "").slice(0, 12) || "connection";
  const digest = createHash("sha256").update(`${connectionId}\0${name}`).digest("hex").slice(0, 10);
  return `mcp_${namespace}_${index}_${digest}`.slice(0, 64);
}

export function sanitizeMcpMetadata(value: unknown, credential: string | null, depth = 0): unknown {
  if (depth > 8) return "[truncated]";
  if (typeof value === "string") {
    const redacted = credential ? value.split(credential).join("[redacted]") : value;
    return redacted.replace(/Bearer\s+[^\s,;\]}"']+/gi, "Bearer [redacted]").slice(0, 4000);
  }
  if (Array.isArray(value)) return value.slice(0, 100).map((item) => sanitizeMcpMetadata(item, credential, depth + 1));
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value as Record<string, unknown>).slice(0, 100).map(([key, item]) => [
    credential ? key.split(credential).join("[redacted]").slice(0, 200) : key.slice(0, 200),
    sanitizeMcpMetadata(item, credential, depth + 1),
  ]));
}

export function sanitizeMcpOutput(value: unknown, credential: string | null): string {
  let serialized: string;
  try {
    serialized = JSON.stringify(sanitizeMcpMetadata(value, credential));
  } catch {
    serialized = "MCP tool returned a non-serializable result";
  }
  return serialized.replace(/\bsk-[A-Za-z0-9_-]{16,}\b/g, "[redacted]").slice(0, 32_000);
}

async function callMcpTool(
  connection: ToolConnectionCredential,
  remoteName: string,
  args: Record<string, unknown>,
  config: RuntimeConfig,
): Promise<{ text: string; isError: boolean }> {
  const url = await assertToolEndpointAllowed(connection.endpoint, config);
  const transport = new StreamableHTTPClientTransport(url, {
    requestInit: {
      redirect: "error",
      ...(connection.auth_token ? { headers: { authorization: `Bearer ${connection.auth_token}` } } : {}),
    },
    redirectPolicy: "same-origin",
    fetch: (input, init) => guardedFetch(config, input, init),
  });
  const client = new Client({ name: "ordivant-runtime", version: "0.2.0" });
  try {
    await client.connect(transport, { timeout: 15_000 });
    const result = await client.callTool({ name: remoteName, arguments: args }, { signal: AbortSignal.timeout(15_000) });
    return { text: sanitizeMcpOutput(result, connection.auth_token), isError: result.isError === true };
  } catch {
    return { text: "MCP tool call failed; the runtime did not retry this operation.", isError: true };
  } finally {
    await client.close().catch(() => undefined);
  }
}

export async function createMcpExtension(
  scopeId: string,
  connections: ToolConnectionCredential[],
  config: RuntimeConfig,
  activeRun: RunLookup,
): Promise<ReturnType<typeof defineExtension>> {
  const tools: ToolRegistration[] = [];
  const names = new Set<string>();
  for (const connection of connections) {
    const endpoint = await assertToolEndpointAllowed(connection.endpoint, config);
    const transport = new StreamableHTTPClientTransport(endpoint, {
      requestInit: {
        redirect: "error",
        ...(connection.auth_token ? { headers: { authorization: `Bearer ${connection.auth_token}` } } : {}),
      },
      redirectPolicy: "same-origin",
      fetch: (input, init) => guardedFetch(config, input, init),
    });
    const client = new Client({ name: "ordivant-runtime", version: "0.2.0" });
    let discovered: McpTool[];
    try {
      await client.connect(transport, { timeout: 15_000 });
      discovered = (await client.listTools({}, { signal: AbortSignal.timeout(15_000) })).tools;
    } catch {
      await client.close().catch(() => undefined);
      throw new Error(`MCP connection ${connection.name} could not list tools`);
    }
    await client.close().catch(() => undefined);
    const allowed = new Set(connection.allowed_tools);
    for (const [index, tool] of discovered.entries()) {
      if (!allowed.has(tool.name)) continue;
      const safeSchema = sanitizeMcpMetadata(tool.inputSchema, connection.auth_token);
      if (!tool.name || tool.name.length > 200 || JSON.stringify(safeSchema).length > 32_768) continue;
      const exposedName = toolName(connection.id, tool.name, index);
      if (names.has(exposedName)) throw new Error("MCP tool namespace collision");
      names.add(exposedName);
      const parameters = Type.Unsafe<Record<string, unknown>>(safeSchema as never);
      tools.push(defineTool({
        name: exposedName,
        description: `[${connection.name}] ${String(sanitizeMcpMetadata(tool.description ?? tool.name, connection.auth_token)).slice(0, 1000)}`,
        parameters,
        replay: "unsafe",
        outputLimits: { maxBytes: 32_000, retain: "head" },
        execute: async (args: Record<string, unknown>, api: ToolExecutionApi) => {
          const run = activeRun(String(api.conversationId));
          if (!run || !run.tool_connections?.some((item) => item.id === connection.id)) {
            return { content: [{ type: "text", text: "MCP connection is not bound to this run." }], isError: true };
          }
          await run.beforeToolOperation?.();
          const result = await callMcpTool(connection, tool.name, args, config);
          return { content: [{ type: "text", text: result.text }], isError: result.isError };
        },
      }));
    }
  }
  const extensionName = `ordivant-mcp-${createHash("sha256").update(scopeId).digest("hex").slice(0, 16)}`;
  return defineExtension({ name: extensionName, tools });
}
