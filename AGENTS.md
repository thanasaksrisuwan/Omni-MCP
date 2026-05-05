## FastAPI Backend MCP Rules (Safety-First)

1. Before changing business logic, call `backend.get_session_flow`.
2. Identify the transaction owner before editing.
3. Do not add `session.commit()` inside services or repositories.
4. Multi-table reservation, stock, or payment writes must use one explicit transaction boundary.
5. Use `async with session.begin():` for SQLAlchemy `AsyncSession`.
6. Do not schedule `BackgroundTasks`, email, webhook, or queue calls inside transaction blocks.
7. Do not use `BackgroundTasks` for critical durable side-effects. Use OutboxEvent.
8. Do not share one `AsyncSession` across concurrent tasks.
9. After editing, run `backend.validate_transaction_usage`.
10. Fix all blocking TX errors before final response.
11. If MCP confidence is below 0.75, inspect the relevant files manually before editing.

## AI Agent Discipline

- `docs/SRS.md` is the source of truth.
- Do not modify `docs/SRS.md` to match implementation mistakes.
- Do not expand scope beyond the current task.
- If requirements are contradictory, report the contradiction instead of editing around it.
- If confidence is low, inspect files manually before editing.