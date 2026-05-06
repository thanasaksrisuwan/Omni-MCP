from __future__ import annotations

import argparse
import ast
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.backend_scanner import (
        DEFAULT_SCAN_DIRS,
        EXCLUDED_DIRS,
        annotation_name,
        dotted_name,
        relative_path,
        route_from_decorator,
        stable_json,
        string_value,
        write_json,
    )
except ModuleNotFoundError:
    from backend_scanner import (
        DEFAULT_SCAN_DIRS,
        EXCLUDED_DIRS,
        annotation_name,
        dotted_name,
        relative_path,
        route_from_decorator,
        stable_json,
        string_value,
        write_json,
    )


RESERVATION_STATES = [
    "draft",
    "pending_payment",
    "paid",
    "confirmed",
    "fulfilled",
    "cancelled",
    "expired",
    "refunded",
]
ALLOWED_TRANSITIONS = {
    "draft": ["pending_payment", "cancelled", "expired"],
    "pending_payment": ["paid", "cancelled", "expired"],
    "paid": ["confirmed", "refunded"],
    "confirmed": ["fulfilled", "cancelled", "refunded"],
    "fulfilled": ["refunded"],
    "cancelled": [],
    "expired": [],
    "refunded": [],
}
TERMINAL_STATES = {"cancelled", "expired", "refunded"}
CRITICAL_PATH_HINTS = {"reservation", "payment", "webhook"}
CRITICAL_SIDE_EFFECT_HINTS = {
    "payment",
    "inventory",
    "reservation",
    "stock",
    "webhook",
    "confirmation",
    "release",
}
SIDE_EFFECT_OPERATION_HINTS = {
    "add_task",
    "send",
    "webhook",
    "dispatch",
    "notify",
    "notification",
    "sync",
    "external",
    "queue",
    "email",
    "charge",
    "confirmation",
}
OUTBOX_NAMES = {"OutboxEvent", "models.OutboxEvent"}
IDEMPOTENCY_NAMES = {"IdempotencyRecord", "IdempotencyKey", "models.IdempotencyRecord"}


@dataclass
class StateTransition:
    function: str
    source_file: str
    line: int
    from_state: str | None
    to_state: str
    hardcoded_status: bool
    confidence: float
    provenance: str = "static-analysis"


@dataclass
class IdempotencyCheck:
    function: str
    source_file: str
    line: int
    route_method: str | None
    route_path: str | None
    is_critical_create_flow: bool
    accepts_idempotency_key: bool
    persists_idempotency_key: bool
    returns_existing_result: bool
    unique_key_visible: bool
    confidence: float
    provenance: str = "static-analysis"


@dataclass
class OutboxEventRecord:
    function: str
    source_file: str
    line: int
    event_type: str | None
    has_idempotency_key: bool
    inside_transaction: bool
    confidence: float
    provenance: str = "static-analysis"


@dataclass
class SideEffectRecord:
    function: str
    source_file: str
    line: int
    call: str
    target: str | None
    inside_transaction: bool
    is_critical: bool
    confidence: float
    provenance: str = "static-analysis"


@dataclass
class InvariantSignal:
    function: str
    source_file: str
    line: int
    signal: str
    confidence: float
    provenance: str = "static-analysis"


@dataclass
class FunctionAnalysis:
    name: str
    source_file: str
    line: int
    is_async: bool
    route_method: str | None
    route_path: str | None
    parameters: list[str]
    idempotency_parameters: list[str]
    transitions: list[StateTransition]
    outbox_events: list[OutboxEventRecord]
    side_effects: list[SideEffectRecord]
    invariant_signals: list[InvariantSignal]
    status_guards: set[str]
    calls: set[str]
    unique_constraints: list[list[str]]
    enum_status_classes: list[str]
    confidence: float
    provenance: str = "static-analysis"


@dataclass
class ValidationIssue:
    code: str
    severity: str
    message: str
    source_file: str
    line: int
    function: str
    confidence: float
    provenance: str = "static-analysis"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def source_hash(files: list[Path]) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(files, key=lambda item: item.as_posix()):
        digest.update(file_path.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def discover_files(project_root: Path, roots: list[Path] | None) -> tuple[list[Path], list[str]]:
    warnings: list[str] = []
    scan_roots: list[Path] = []

    if roots:
        scan_roots = [root if root.is_absolute() else project_root / root for root in roots]
    else:
        for name in DEFAULT_SCAN_DIRS:
            candidate = project_root / name
            if candidate.exists():
                scan_roots.append(candidate)

    if not scan_roots:
        warnings.append("No default backend source directories found: app, backend, src")
        return [], warnings

    files: list[Path] = []
    for root in scan_roots:
        if root.is_file() and root.suffix == ".py":
            files.append(root)
            continue
        if not root.exists():
            warnings.append(f"Scan root does not exist: {relative_path(root, project_root)}")
            continue
        for file_path in root.rglob("*.py"):
            if any(part in EXCLUDED_DIRS for part in file_path.relative_to(project_root).parts):
                continue
            files.append(file_path)

    return sorted(set(files)), warnings


def iter_parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[tuple[ast.arg, ast.AST | None]]:
    positional_defaults = [None] * (len(node.args.args) - len(node.args.defaults)) + list(node.args.defaults)
    parameters = list(zip(node.args.args, positional_defaults, strict=False))
    parameters.extend(zip(node.args.kwonlyargs, node.args.kw_defaults, strict=False))
    return parameters


def keyword_value(call: ast.Call, name: str) -> ast.AST | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def status_value(node: ast.AST | None) -> tuple[str | None, bool]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        lowered = node.value.lower()
        if lowered in RESERVATION_STATES:
            return lowered, True
        return None, True
    name = dotted_name(node)
    if not name:
        return None, False
    status = name.split(".")[-1].lower()
    if status in RESERVATION_STATES:
        return status, False
    return None, False


def call_name_parts(call_name: str | None) -> set[str]:
    if not call_name:
        return set()
    normalized = call_name.replace(".", "_").replace("-", "_").lower()
    return {part for part in normalized.split("_") if part}


def is_session_begin_call(expr: ast.AST) -> bool:
    if not isinstance(expr, ast.Call):
        return False
    if not isinstance(expr.func, ast.Attribute):
        return False
    return expr.func.attr == "begin"


def call_target_name(call: ast.Call) -> str | None:
    if not call.args:
        return None
    return dotted_name(call.args[0])


def target_model_from_session_add(call: ast.Call) -> ast.Call | None:
    if not isinstance(call.func, ast.Attribute) or call.func.attr != "add":
        return None
    if not call.args or not isinstance(call.args[0], ast.Call):
        return None
    return call.args[0]


def constructor_name(call: ast.Call) -> str | None:
    name = dotted_name(call.func)
    if not name:
        return None
    return name.split(".")[-1]


def string_keyword(call: ast.Call, name: str) -> str | None:
    value = keyword_value(call, name)
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    return None


def has_keyword_name(call: ast.Call, keyword_name: str) -> bool:
    return any(keyword.arg == keyword_name for keyword in call.keywords)


def unique_constraints(tree: ast.AST) -> list[list[str]]:
    constraints: list[list[str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = dotted_name(node.func)
        if not name or not name.endswith("UniqueConstraint"):
            continue
        values = [value for value in (string_value(arg) for arg in node.args) if value]
        if values:
            constraints.append(values)
    return constraints


def enum_status_classes(tree: ast.AST) -> list[str]:
    classes: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        base_names = {dotted_name(base) for base in node.bases}
        if "Enum" in base_names or "enum.Enum" in base_names or node.name.endswith("Status"):
            if "Status" in node.name:
                classes.append(node.name)
    return classes


def has_unique_idempotency_key(constraints: list[list[str]]) -> bool:
    for constraint in constraints:
        normalized = {item.lower() for item in constraint}
        if "idempotency_key" in normalized or "key" in normalized:
            return True
    return False


def has_unique_outbox_key(constraints: list[list[str]]) -> bool:
    for constraint in constraints:
        normalized = {item.lower() for item in constraint}
        if {"event_type", "idempotency_key"}.issubset(normalized):
            return True
    return False


def is_idempotency_parameter(arg: ast.arg, default: ast.AST | None) -> bool:
    if "idempotency" in arg.arg.lower():
        return True
    if not isinstance(default, ast.Call):
        return False
    if not (dotted_name(default.func) or "").endswith("Header"):
        return False
    alias = string_keyword(default, "alias")
    convert_underscores = keyword_value(default, "convert_underscores")
    if alias == "X-Idempotency-Key":
        return True
    return arg.arg.lower() in {"x_idempotency_key", "idempotency_key"} and convert_underscores is not None


def route_is_critical_create(route_method: str | None, route_path: str | None, function_name: str) -> bool:
    if route_method != "POST":
        return False
    haystack = f"{route_path or ''} {function_name}".lower()
    return any(hint in haystack for hint in CRITICAL_PATH_HINTS)


def is_background_task_call(call_name: str | None) -> bool:
    return call_name is not None and call_name.endswith("add_task")


def side_effect_is_critical(call_name: str | None, target: str | None) -> bool:
    haystack = f"{call_name or ''} {target or ''}".lower()
    return any(hint in haystack for hint in CRITICAL_SIDE_EFFECT_HINTS)


def looks_like_side_effect_operation(call_name: str | None, target: str | None) -> bool:
    haystack = f"{call_name or ''} {target or ''}".lower()
    return any(hint in haystack for hint in SIDE_EFFECT_OPERATION_HINTS)


class FunctionVisitor(ast.NodeVisitor):
    def __init__(self, analysis: FunctionAnalysis):
        self.analysis = analysis
        self.transaction_stack: list[int] = []
        self.status_guard_stack: list[str] = []
        self.quantity_guard_stack = 0

    def visit_With(self, node: ast.With) -> None:
        self._visit_with(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._visit_with(node)

    def _visit_with(self, node: ast.With | ast.AsyncWith) -> None:
        has_begin = any(is_session_begin_call(item.context_expr) for item in node.items)
        if has_begin:
            self.transaction_stack.append(getattr(node, "lineno", 0))
            for statement in node.body:
                self.visit(statement)
            self.transaction_stack.pop()
            return
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        guard_statuses = self._status_guards_from_test(node.test)
        has_quantity_guard = self._has_quantity_guard(node.test)

        if has_quantity_guard:
            self.quantity_guard_stack += 1
            self.analysis.invariant_signals.append(
                InvariantSignal(
                    function=self.analysis.name,
                    source_file=self.analysis.source_file,
                    line=getattr(node, "lineno", 0),
                    signal="stock_lock_quantity_guard",
                    confidence=0.85,
                )
            )

        for status in guard_statuses:
            self.analysis.status_guards.add(status)
            self.status_guard_stack.append(status)

        for statement in node.body:
            self.visit(statement)

        for _status in guard_statuses:
            self.status_guard_stack.pop()

        if has_quantity_guard:
            self.quantity_guard_stack -= 1

        for statement in node.orelse:
            self.visit(statement)

    def _status_guards_from_test(self, node: ast.AST) -> list[str]:
        statuses: list[str] = []
        for child in ast.walk(node):
            if not isinstance(child, ast.Compare):
                continue
            operands = [child.left, *child.comparators]
            for operand in operands:
                status, _hardcoded = status_value(operand)
                if status:
                    statuses.append(status)
        return statuses

    def _has_quantity_guard(self, node: ast.AST) -> bool:
        for child in ast.walk(node):
            if not isinstance(child, ast.Compare):
                continue
            text = ast.unparse(child).lower() if hasattr(ast, "unparse") else ""
            if "quantity" in text and "available" in text:
                return True
        return False

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._record_status_assignment(target, node.value, getattr(node, "lineno", 0))
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._record_status_assignment(node.target, node.value, getattr(node, "lineno", 0))
        self.generic_visit(node)

    def _record_status_assignment(self, target: ast.AST, value: ast.AST, line: int) -> None:
        if not isinstance(target, ast.Attribute) or target.attr != "status":
            return
        to_state, hardcoded = status_value(value)
        if not to_state:
            return
        from_state = self.status_guard_stack[-1] if self.status_guard_stack else None
        self.analysis.transitions.append(
            StateTransition(
                function=self.analysis.name,
                source_file=self.analysis.source_file,
                line=line,
                from_state=from_state,
                to_state=to_state,
                hardcoded_status=hardcoded,
                confidence=0.9 if from_state else 0.75,
            )
        )

    def visit_Call(self, node: ast.Call) -> None:
        call_name = dotted_name(node.func) or "unknown"
        self.analysis.calls.add(call_name)
        self._record_session_add(node)
        self._record_named_signal(node, call_name)
        self._record_side_effect(node, call_name)
        self.generic_visit(node)

    def _record_session_add(self, node: ast.Call) -> None:
        constructor_call = target_model_from_session_add(node)
        if constructor_call is None:
            return
        name = constructor_name(constructor_call)
        if not name:
            return
        line = getattr(node, "lineno", 0)

        if name in {item.split(".")[-1] for item in IDEMPOTENCY_NAMES}:
            self.analysis.invariant_signals.append(self._signal("idempotency_persisted", line))
            return

        if name in {item.split(".")[-1] for item in OUTBOX_NAMES}:
            self.analysis.outbox_events.append(
                OutboxEventRecord(
                    function=self.analysis.name,
                    source_file=self.analysis.source_file,
                    line=line,
                    event_type=string_keyword(constructor_call, "event_type"),
                    has_idempotency_key=has_keyword_name(constructor_call, "idempotency_key"),
                    inside_transaction=bool(self.transaction_stack),
                    confidence=0.9,
                )
            )
            return

        if name == "Payment":
            status = (string_keyword(constructor_call, "status") or "").lower()
            if status == "settled":
                self.analysis.invariant_signals.append(self._signal("settled_payment", line))
            return

        if name == "PaymentTransaction":
            kind = (string_keyword(constructor_call, "kind") or string_keyword(constructor_call, "type") or "").lower()
            if kind == "refund":
                self.analysis.invariant_signals.append(self._signal("refund_transaction", line))
            return

        if name == "StockLock":
            self.analysis.invariant_signals.append(self._signal("stock_lock_created", line))
            if self.quantity_guard_stack:
                self.analysis.invariant_signals.append(self._signal("stock_lock_quantity_guard", line))

    def _record_named_signal(self, node: ast.Call, call_name: str) -> None:
        lowered = call_name.lower()
        line = getattr(node, "lineno", 0)

        signal_by_hint = {
            "get_existing_idempotency": "idempotency_lookup",
            "return_existing_response": "idempotency_lookup",
            "persist_idempotency": "idempotency_persisted",
            "release_active_stock_lock": "stock_released",
            "release_stock_lock": "stock_released",
            "deactivate_stock_lock": "stock_released",
            "ensure_stock_lock": "stock_validated",
            "consume_stock_lock": "stock_validated",
            "validate_stock_lock": "stock_validated",
            "mark_payment_settled": "settled_payment",
            "create_refund_transaction": "refund_transaction",
            "validate_stock_lock_quantity": "stock_lock_quantity_guard",
        }
        for hint, signal in signal_by_hint.items():
            if hint in lowered:
                self.analysis.invariant_signals.append(self._signal(signal, line))

        if "enqueue_outbox" in lowered or "add_outbox" in lowered:
            self.analysis.outbox_events.append(
                OutboxEventRecord(
                    function=self.analysis.name,
                    source_file=self.analysis.source_file,
                    line=line,
                    event_type=string_keyword(node, "event_type"),
                    has_idempotency_key=has_keyword_name(node, "idempotency_key"),
                    inside_transaction=bool(self.transaction_stack),
                    confidence=0.85,
                )
            )

    def _record_side_effect(self, node: ast.Call, call_name: str) -> None:
        if "outbox" in call_name.lower():
            return
        target = call_target_name(node) if is_background_task_call(call_name) else None
        if not (is_background_task_call(call_name) or looks_like_side_effect_operation(call_name, target)):
            return
        is_critical = side_effect_is_critical(call_name, target)
        self.analysis.side_effects.append(
            SideEffectRecord(
                function=self.analysis.name,
                source_file=self.analysis.source_file,
                line=getattr(node, "lineno", 0),
                call=call_name,
                target=target,
                inside_transaction=bool(self.transaction_stack),
                is_critical=is_critical,
                confidence=0.85,
            )
        )

    def _signal(self, signal: str, line: int) -> InvariantSignal:
        return InvariantSignal(
            function=self.analysis.name,
            source_file=self.analysis.source_file,
            line=line,
            signal=signal,
            confidence=0.85,
        )


def analyze_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    source_file: str,
    route_method: str | None,
    route_path: str | None,
    constraints: list[list[str]],
    status_classes: list[str],
) -> FunctionAnalysis:
    parameters: list[str] = []
    idempotency_parameters: list[str] = []
    for arg, default in iter_parameters(node):
        parameters.append(arg.arg)
        if is_idempotency_parameter(arg, default):
            idempotency_parameters.append(arg.arg)

    analysis = FunctionAnalysis(
        name=node.name,
        source_file=source_file,
        line=getattr(node, "lineno", 0),
        is_async=isinstance(node, ast.AsyncFunctionDef),
        route_method=route_method,
        route_path=route_path,
        parameters=parameters,
        idempotency_parameters=idempotency_parameters,
        transitions=[],
        outbox_events=[],
        side_effects=[],
        invariant_signals=[],
        status_guards=set(),
        calls=set(),
        unique_constraints=constraints,
        enum_status_classes=status_classes,
        confidence=0.9 if route_method or "reservation" in node.name.lower() else 0.8,
    )
    FunctionVisitor(analysis).visit(node)
    return analysis


def analyze_file(file_path: Path, project_root: Path) -> list[FunctionAnalysis]:
    source_file = relative_path(file_path, project_root)
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=source_file)
    constraints = unique_constraints(tree)
    status_classes = enum_status_classes(tree)
    analyses: list[FunctionAnalysis] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        route_decorators = [
            route
            for decorator in node.decorator_list
            if (route := route_from_decorator(decorator)) is not None
        ]
        if route_decorators:
            for method, path, _line in route_decorators:
                analyses.append(
                    analyze_function(
                        node,
                        source_file=source_file,
                        route_method=method,
                        route_path=path,
                        constraints=constraints,
                        status_classes=status_classes,
                    )
                )
        else:
            analyses.append(
                analyze_function(
                    node,
                    source_file=source_file,
                    route_method=None,
                    route_path=None,
                    constraints=constraints,
                    status_classes=status_classes,
                )
            )

    return analyses


def issue(
    code: str,
    severity: str,
    message: str,
    analysis: FunctionAnalysis,
    line: int | None = None,
    confidence: float = 0.9,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=severity,
        message=message,
        source_file=analysis.source_file,
        line=line or analysis.line,
        function=analysis.name,
        confidence=confidence,
    )


def signal_names(analysis: FunctionAnalysis) -> set[str]:
    return {signal.signal for signal in analysis.invariant_signals}


def validate_state_analyses(analyses: list[FunctionAnalysis]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for analysis in analyses:
        for transition in analysis.transitions:
            if transition.from_state is not None:
                allowed = ALLOWED_TRANSITIONS.get(transition.from_state, [])
                if transition.to_state not in allowed:
                    issues.append(
                        issue(
                            "STATE001",
                            "error",
                            f"Invalid reservation state transition: {transition.from_state} -> {transition.to_state}.",
                            analysis,
                            transition.line,
                            transition.confidence,
                        )
                    )
            if analysis.enum_status_classes and transition.hardcoded_status:
                issues.append(
                    issue(
                        "STATE002",
                        "warning",
                        "Hardcoded reservation status string used while a status Enum is visible.",
                        analysis,
                        transition.line,
                        0.85,
                    )
                )
    return issues


def validate_idempotency_analyses(analyses: list[FunctionAnalysis]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for analysis in analyses:
        if not route_is_critical_create(analysis.route_method, analysis.route_path, analysis.name):
            continue
        signals = signal_names(analysis)
        if not analysis.idempotency_parameters:
            issues.append(
                issue(
                    "IDEMP001",
                    "error",
                    "Critical create flow does not accept X-Idempotency-Key.",
                    analysis,
                    confidence=0.95,
                )
            )
        if "idempotency_persisted" not in signals:
            issues.append(
                issue(
                    "IDEMP002",
                    "error",
                    "Critical create flow does not persist an idempotency key.",
                    analysis,
                    confidence=0.9,
                )
            )
        if not has_unique_idempotency_key(analysis.unique_constraints):
            issues.append(
                issue(
                    "IDEMP003",
                    "error",
                    "Durable uniqueness for the idempotency key is not visible.",
                    analysis,
                    confidence=0.85,
                )
            )
        if "idempotency_lookup" not in signals:
            issues.append(
                issue(
                    "IDEMP004",
                    "error",
                    "Retry behavior is not visible; no existing idempotency result lookup was detected.",
                    analysis,
                    confidence=0.85,
                )
            )
    return issues


def validate_outbox_analyses(analyses: list[FunctionAnalysis]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for analysis in analyses:
        critical_side_effects = [effect for effect in analysis.side_effects if effect.is_critical]
        has_outbox = any(event.has_idempotency_key for event in analysis.outbox_events)
        for effect in critical_side_effects:
            if is_background_task_call(effect.call):
                issues.append(
                    issue(
                        "OUTBOX002",
                        "error",
                        f"BackgroundTasks used for critical side-effect `{effect.target or effect.call}`.",
                        analysis,
                        effect.line,
                        effect.confidence,
                    )
                )
            if not has_outbox:
                issues.append(
                    issue(
                        "OUTBOX001",
                        "error",
                        f"Critical side-effect `{effect.target or effect.call}` is not represented by an OutboxEvent.",
                        analysis,
                        effect.line,
                        effect.confidence,
                    )
                )
        for event in analysis.outbox_events:
            if not event.has_idempotency_key:
                issues.append(
                    issue(
                        "OUTBOX003",
                        "error",
                        "OutboxEvent does not include an idempotency_key.",
                        analysis,
                        event.line,
                        event.confidence,
                    )
                )
        if analysis.outbox_events and not has_unique_outbox_key(analysis.unique_constraints):
            issues.append(
                issue(
                    "OUTBOX004",
                    "error",
                    "unique(event_type, idempotency_key) is not visible for outbox events.",
                    analysis,
                    confidence=0.85,
                )
            )
    return issues


def validate_invariant_analyses(analyses: list[FunctionAnalysis]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for analysis in analyses:
        signals = signal_names(analysis)
        target_states = {transition.to_state for transition in analysis.transitions}

        if "expired" in target_states and "stock_released" not in signals:
            issues.append(issue("INV001", "error", "Expired reservation does not visibly release active stock locks.", analysis))
        if "paid" in target_states and "settled_payment" not in signals:
            issues.append(issue("INV002", "error", "Paid reservation does not visibly require a settled payment.", analysis))
        if "confirmed" in target_states and "stock_validated" not in signals:
            issues.append(issue("INV003", "error", "Confirmed reservation does not visibly validate or consume stock locks.", analysis))
        if "cancelled" in target_states and "stock_released" not in signals:
            issues.append(issue("INV004", "error", "Cancelled reservation does not visibly release stock.", analysis))
        if "refunded" in target_states and "refund_transaction" not in signals:
            issues.append(issue("INV005", "error", "Refunded reservation does not visibly create a refund transaction.", analysis))
        if "expired" in target_states and "expired" not in analysis.status_guards:
            issues.append(issue("INV006", "error", "Reservation expiration does not appear idempotent.", analysis))
        if "stock_lock_created" in signals and "stock_lock_quantity_guard" not in signals:
            issues.append(issue("INV007", "error", "Stock lock quantity is not visibly guarded against available quantity.", analysis))
    return issues


def validation_payload(issues: list[ValidationIssue], rules_checked: list[str]) -> dict[str, Any]:
    has_errors = any(item.severity == "error" for item in issues)
    return {
        "status": "failed" if has_errors else "ok",
        "errors": [asdict(item) for item in issues if item.severity == "error"],
        "warnings": [asdict(item) for item in issues if item.severity == "warning"],
        "rules_checked": rules_checked,
    }


def state_machine_record(analyses: list[FunctionAnalysis], issues: list[ValidationIssue]) -> dict[str, Any]:
    return {
        "name": "reservation",
        "states": RESERVATION_STATES,
        "terminal_states": sorted(TERMINAL_STATES),
        "allowed_transitions": ALLOWED_TRANSITIONS,
        "detected_transitions": [asdict(transition) for analysis in analyses for transition in analysis.transitions],
        "validation": validation_payload(issues, ["STATE001", "STATE002"]),
        "confidence": 0.9,
        "provenance": "static-analysis",
    }


def idempotency_records(analyses: list[FunctionAnalysis]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for analysis in analyses:
        if not route_is_critical_create(analysis.route_method, analysis.route_path, analysis.name):
            continue
        signals = signal_names(analysis)
        records.append(
            asdict(
                IdempotencyCheck(
                    function=analysis.name,
                    source_file=analysis.source_file,
                    line=analysis.line,
                    route_method=analysis.route_method,
                    route_path=analysis.route_path,
                    is_critical_create_flow=True,
                    accepts_idempotency_key=bool(analysis.idempotency_parameters),
                    persists_idempotency_key="idempotency_persisted" in signals,
                    returns_existing_result="idempotency_lookup" in signals,
                    unique_key_visible=has_unique_idempotency_key(analysis.unique_constraints),
                    confidence=0.9,
                )
            )
        )
    return records


def generate_manifests(project_root: Path, output_dir: Path, roots: list[Path] | None = None) -> dict[str, Any]:
    generated_at = utc_now()
    files, warnings = discover_files(project_root, roots)
    analyses: list[FunctionAnalysis] = []
    for file_path in files:
        analyses.extend(analyze_file(file_path, project_root))

    if not files:
        warnings.append("No Python backend files were scanned; reservation safety is not proven")

    state_issues = validate_state_analyses(analyses)
    idempotency_issues = validate_idempotency_analyses(analyses)
    outbox_issues = validate_outbox_analyses(analyses)
    invariant_issues = validate_invariant_analyses(analyses)
    all_issues = state_issues + idempotency_issues + outbox_issues + invariant_issues

    has_errors = any(validation_issue.severity == "error" for validation_issue in all_issues)
    status = "failed" if has_errors else ("ok" if files else "needs_manual_review")
    risk = "high" if has_errors else ("low" if files else "unknown")
    confidence = 0.9 if files else 0.5
    digest = source_hash(files) if files else hashlib.sha256(b"").hexdigest()
    common = {
        "schema_version": "1.0.0",
        "generated_at": generated_at,
        "project_root": str(project_root),
        "source_hash": digest,
        "confidence": confidence,
        "status": status,
        "risk": risk,
        "parser": "ast",
        "preferred_parser": "libcst",
        "warnings": warnings,
        "files_scanned": [relative_path(path, project_root) for path in files],
    }

    state_machines = {
        **common,
        "scanner": "backend_reservation_state_machine",
        "state_machines": [state_machine_record(analyses, state_issues)],
    }
    outbox_events = {
        **common,
        "scanner": "backend_reservation_idempotency_outbox",
        "idempotency": {
            "records": idempotency_records(analyses),
            "validation": validation_payload(
                idempotency_issues,
                ["IDEMP001", "IDEMP002", "IDEMP003", "IDEMP004"],
            ),
        },
        "outbox_events": [asdict(event) for analysis in analyses for event in analysis.outbox_events],
        "side_effects": [asdict(effect) for analysis in analyses for effect in analysis.side_effects],
        "outbox_validation": validation_payload(
            outbox_issues,
            ["OUTBOX001", "OUTBOX002", "OUTBOX003", "OUTBOX004"],
        ),
    }
    invariants = {
        **common,
        "scanner": "backend_reservation_invariants",
        "invariant_signals": [asdict(signal) for analysis in analyses for signal in analysis.invariant_signals],
        "validation": validation_payload(
            invariant_issues,
            ["INV001", "INV002", "INV003", "INV004", "INV005", "INV006", "INV007"],
        ),
    }

    write_json(output_dir / "state-machines.json", state_machines)
    write_json(output_dir / "outbox-events.json", outbox_events)
    write_json(output_dir / "invariants.json", invariants)
    return {
        "state_machines": state_machines,
        "outbox_events": outbox_events,
        "invariants": invariants,
    }


def get_state_machine(state_machines_manifest: dict[str, Any], name: str = "reservation") -> dict[str, Any]:
    for machine in state_machines_manifest.get("state_machines", []):
        if machine.get("name") == name:
            return {
                "status": "ok",
                "risk": state_machines_manifest.get("risk", "unknown"),
                "confidence": machine.get("confidence", 0.0),
                "state_machine": machine,
            }
    return {
        "status": "needs_manual_review",
        "risk": "unknown",
        "reason": f"No state machine found for {name}",
    }


def validate_state_transition(state_machines_manifest: dict[str, Any]) -> dict[str, Any]:
    machines = state_machines_manifest.get("state_machines", [])
    if not machines:
        return {"status": "needs_manual_review", "risk": "unknown", "reason": "No state machines found"}
    return machines[0].get("validation", {"status": "needs_manual_review", "risk": "unknown"})


def validate_idempotency(outbox_events_manifest: dict[str, Any]) -> dict[str, Any]:
    idempotency = outbox_events_manifest.get("idempotency")
    if not idempotency:
        return {"status": "needs_manual_review", "risk": "unknown", "reason": "No idempotency section found"}
    return idempotency.get("validation", {"status": "needs_manual_review", "risk": "unknown"})


def validate_outbox_usage(outbox_events_manifest: dict[str, Any]) -> dict[str, Any]:
    validation = outbox_events_manifest.get("outbox_validation")
    if not validation:
        return {"status": "needs_manual_review", "risk": "unknown", "reason": "No outbox validation found"}
    return validation


def validate_reservation_invariants(invariants_manifest: dict[str, Any]) -> dict[str, Any]:
    validation = invariants_manifest.get("validation")
    if not validation:
        return {"status": "needs_manual_review", "risk": "unknown", "reason": "No invariant validation found"}
    return validation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Backend Reservation Safety manifests.")
    parser.add_argument("--project-root", default=".", help="Project root used for relative paths.")
    parser.add_argument("--root", action="append", dest="roots", help="Python file or directory to scan. May be repeated.")
    parser.add_argument("--output", default=".backend-ai", help="Output directory for generated manifests.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    output_dir = Path(args.output)
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir
    roots = [Path(root) for root in args.roots] if args.roots else None
    result = generate_manifests(project_root, output_dir, roots)
    state_validation = validate_state_transition(result["state_machines"])
    idempotency_validation = validate_idempotency(result["outbox_events"])
    outbox_validation = validate_outbox_usage(result["outbox_events"])
    invariant_validation = validate_reservation_invariants(result["invariants"])
    print(
        stable_json(
            {
                "status": result["state_machines"]["status"],
                "risk": result["state_machines"]["risk"],
                "state_errors": len(state_validation.get("errors", [])),
                "idempotency_errors": len(idempotency_validation.get("errors", [])),
                "outbox_errors": len(outbox_validation.get("errors", [])),
                "invariant_errors": len(invariant_validation.get("errors", [])),
                "output": str(output_dir),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
