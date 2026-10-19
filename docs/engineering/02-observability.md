# Observability Strategy

> Observability is treated as a core engineering capability rather than an operational afterthought.

---

## Philosophy

Every important action performed by the system should be observable.

Developers should understand:

- what happened
- why it happened
- how long it took
- how much it cost

without reproducing the issue.

---

## Layers

### Application

- Structured logging
- Startup logs report whether Langfuse observability is enabled or safely disabled.

### Workflow

- LangGraph state transitions
- Agent graph invocation is wrapped in a root workflow observation.
- When Langfuse is enabled, the LangGraph callback handler is passed through
  invocation config.

### LLM

- Langfuse traces
- Prompt history
- Token usage
- Latency
- Cost
- Direct OpenAI Responses API calls made by Rastin-AI adapters are traced as
  generation observations.
- Provider-reported token usage is forwarded when available. Rastin-AI does
  not estimate token counts or calculate billing.

### Tools

- Deterministic ExecutionPlan tasks are traced as tool observations at the
  central executor boundary.
- Tool input and output are bounded and redacted before tracing.
- Tool exceptions keep the existing application behavior while recording a safe
  error status in the trace.

### Infrastructure

Future:

- OpenTelemetry
- Prometheus
- Grafana

---

## Principles

- Every workflow has a trace ID.
- Every tool execution is observable.
- Every LLM call is traceable.
- Errors should include contextual information.
- Logs should be structured and machine-readable.
- Observability must not be a single point of failure.
- Langfuse imports are lazy so disabled deployments behave normally.
- Secrets, credentials, binary payloads, and oversized values are not sent
  directly to telemetry.

---

## Langfuse Configuration

Langfuse tracing is optional and disabled by default.

Required variables to enable tracing:

```env
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=http://localhost:3000
```

`LANGFUSE_BASE_URL` should point at the Langfuse API host. For a local Docker
Compose stack this is usually `http://localhost:3000`; for Langfuse Cloud use the
project's configured region URL.

If `LANGFUSE_ENABLED=true` but either key is missing, Rastin-AI logs that
observability is disabled and continues running.

---

## Traced Data

Rastin-AI sends the following non-sensitive telemetry when enabled:

- Workflow executions: root agent/workflow observation, environment, app version,
  and bounded input/output.
- LangGraph execution: Langfuse LangChain callback handler through graph config.
- LLM calls: model name, input, output, provider token usage, errors, and latency.
- Tool calls: capability name, task ID, validated arguments, bounded result,
  errors, and latency.

Latency is measured by Langfuse observation durations. Developers can inspect
these traces in the configured Langfuse project.

---

## Future

- OpenTelemetry
- Distributed tracing
- Metrics dashboards
- Alerting
