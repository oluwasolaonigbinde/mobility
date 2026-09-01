import ipaddress
import json
import logging
import re
from datetime import UTC, datetime

import sentry_sdk

from app.core.config import Settings
from app.core.middleware import get_request_id

_REDACTED = "[REDACTED]"
_CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_ALWAYS_SENSITIVE_KEY = re.compile(
    r"(?i)^(authorization|cookie|token|password|secret|api[_-]?key|nin|bvn|"
    r"kyc|fraud(?:[_-]?evidence)?|evidence|bank(?:[_-]?account)?|lat(?:itude)?|"
    r"lon(?:gitude)?|gps|coord(?:inate)?s?|(?:private|signed|presigned|download|"
    r"storage|object)[_-]?url|url)$"
)
_MAX_ASSIGNMENTS = 1024
_MAX_SERIALIZED_DEPTH = _MAX_ASSIGNMENTS
_MAX_SERIALIZED_STRUCTURES = _MAX_ASSIGNMENTS * 4
_MAX_STRUCTURED_DEPTH = 128
_MAX_STRUCTURED_NODES = 4096
_QUOTE_ENDS = {"'": "'", '"': '"', "‘": "’", "“": "”"}
_QUOTE_SYMBOLS = frozenset((*_QUOTE_ENDS, *_QUOTE_ENDS.values()))
_QUOTED_KEY_CANDIDATE = re.compile(
    r"(?i)(?P<opening>['\"‘’“”])(?P<key>\.*[a-z][a-z0-9_.-]*+)"
    r"(?P<closing>['\"‘’“”])(?=\s*[=:：＝])"
)
_ASSIGNMENT_BOUNDARY = re.compile(
    r'(?:"\.*[A-Za-z][A-Za-z0-9_.-]*"|'
    r"'\.*[A-Za-z][A-Za-z0-9_.-]*'|"
    r"‘\.*[A-Za-z][A-Za-z0-9_.-]*’|“\.*[A-Za-z][A-Za-z0-9_.-]*”|"
    r"\.*[a-z][A-Za-z0-9_.-]*)\s*[=:：＝]"
)
_ASSIGNMENT = re.compile(
    r"(?i)(?:(?P<ascii_quote>['\"])(?P<ascii_key>\.*[a-z][a-z0-9_.-]*+)"
    r"(?P=ascii_quote)|‘(?P<smart_single_key>\.*[a-z][a-z0-9_.-]*+)’|"
    r"“(?P<smart_double_key>\.*[a-z][a-z0-9_.-]*+)”|"
    r"(?<![a-z0-9_.-])(?P<unquoted_key>\.*[a-z][a-z0-9_.-]*+))"
    r"(?P<separator>\s*[=:：＝]\s*)"
)
_EMAIL_VALUE = re.compile(
    r"(?i)(?<![a-z0-9.!#$%&'*+/?^_`{|}~-])"
    r"[a-z0-9.!#$%&'*+/?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+(?![a-z0-9-])"
)
_PHONE_VALUE = re.compile(
    r"(?<![\w])(?:\+\d(?:[\s().-]*\d){7,14}|"
    r"0(?=\d*[\s().-]+\d)\d(?:[\s().-]*\d){8,13}|"
    r"\(\d{2,4}\)(?:[\s.-]*\d){6,12})(?![\w])"
)
_IPV4_VALUE = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
_IPV6_VALUE = re.compile(r"(?i)(?<![0-9a-f:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?![0-9a-f:])")
_PERSON_CONTEXT_PARTS = frozenset(
    {
        "actor",
        "applicant",
        "approver",
        "contact",
        "consumer",
        "customer",
        "driver",
        "owner",
        "person",
        "personal",
        "recipient",
        "reviewer",
        "sender",
        "user",
    }
)
_BUSINESS_CONTEXT_PARTS = frozenset(
    {
        "business",
        "campaign",
        "company",
        "entity",
        "organization",
        "partner",
        "vendor",
    }
)
_CREDENTIAL_KEY_PARTS = frozenset({"authorization", "cookie", "password", "secret", "token"})
_IDENTITY_KEY_PARTS = frozenset({"bvn", "nin", "passport"})
_SAFE_BANK_ACCOUNT_DIAGNOSTIC_KEYS = frozenset(
    {
        "bank_account_match_confirmed",
        "bank_account_version",
        "bank_account_version_id",
    }
)
_SAFE_BANK_ACCOUNT_DOTTED_PATHS = frozenset(
    {
        ("bank_account", "match_confirmed"),
        ("bank_account", "version"),
        ("bank_account", "version_id"),
    }
)
_PERSON_NAME_KEYS = frozenset(
    {
        "first_name",
        "given_name",
        "last_name",
        "maiden_name",
        "middle_name",
        "preferred_name",
        "surname",
    }
)
_POSTAL_ADDRESS_SUFFIXES = (
    "_address",
    "_address_line",
    "_address_line_1",
    "_address_line_2",
    "_building_number",
    "_house_number",
    "_postal_code",
    "_postcode",
    "_street",
    "_street_address",
    "_street_name",
    "_zip",
    "_zip_code",
    "_zipcode",
)
_RAW_IP_KEYS = frozenset(
    {
        "client_ip",
        "forwarded_for",
        "ip",
        "ip_address",
        "originating_ip",
        "raw_ip",
        "remote_addr",
        "remote_address",
        "remote_ip",
        "source_ip",
        "x_forwarded_for",
        "x_real_ip",
    }
)
_POSTAL_ADDRESS_KEYS = frozenset(
    {
        "address",
        "address_line",
        "address_line_1",
        "address_line_2",
        "building_number",
        "home_address",
        "house_number",
        "line1",
        "line2",
        "line_1",
        "line_2",
        "mailing_address",
        "physical_address",
        "postal_address",
        "postal_code",
        "postcode",
        "residential_address",
        "street",
        "street_address",
        "street_name",
        "zip",
        "zip_code",
        "zipcode",
    }
)
_PERSON_ADDRESS_KEYS = frozenset(
    {
        "contact_address",
        "home_address",
        "mailing_address",
        "personal_address",
        "physical_address",
        "residential_address",
    }
)


def _normalize_key(key: object) -> str:
    words = _CAMEL_CASE_BOUNDARY.sub("_", str(key))
    return re.sub(r"[^a-z0-9]+", "_", words.lower()).strip("_")


def _normalized_parts(value: object) -> set[str]:
    parts = {part for part in _normalize_key(value).split("_") if part}
    parts.update(part[:-1] for part in tuple(parts) if part.endswith("s"))
    return parts


def _normalized_tokens(value: object) -> tuple[str, ...]:
    return tuple(part for part in _normalize_key(value).split("_") if part)


def _semantic_kind(value: object) -> str | None:
    for token in reversed(_normalized_tokens(value)):
        candidates = {token}
        if token.endswith("s") and not token.endswith("ss"):
            candidates.add(token[:-1])
        if candidates & _PERSON_CONTEXT_PARTS:
            return "person"
        if candidates & _BUSINESS_CONTEXT_PARTS:
            return "business"
    return None


def _nearest_context_kind(contexts: tuple[str, ...]) -> str | None:
    for context in reversed(contexts):
        if kind := _semantic_kind(context):
            return kind
    return None


def _has_sensitive_key_family(normalized: str) -> bool:
    tokens = _normalized_tokens(normalized)
    token_set = set(tokens)
    return bool(
        token_set & _CREDENTIAL_KEY_PARTS
        or token_set & _IDENTITY_KEY_PARTS
        or {"api", "key"} <= token_set
        or (
            {"bank", "account"} <= token_set
            and normalized not in _SAFE_BANK_ACCOUNT_DIAGNOSTIC_KEYS
        )
        or (
            len(tokens) >= 3
            and any(
                tokens[index : index + 3] == ("date", "of", "birth")
                for index in range(len(tokens) - 2)
            )
        )
    )


def _is_sensitive_key(key: object, contexts: tuple[str, ...] = ()) -> bool:
    normalized = _normalize_key(key)
    if _ALWAYS_SENSITIVE_KEY.fullmatch(normalized):
        return True
    if normalized.startswith("masked_"):
        return False
    if _has_sensitive_key_family(normalized):
        return True
    if normalized.endswith(("_digest", "_fingerprint", "_hash")):
        return False

    if normalized in _RAW_IP_KEYS:
        return True
    if normalized in {"user_name", "username"}:
        return True
    if normalized == "email" or normalized.endswith(("_email", "_email_address")):
        return True
    if normalized in {
        "cell_phone",
        "cellphone",
        "mobile",
        "mobile_number",
        "phone",
        "phone_number",
        "telephone",
        "telephone_number",
    } or normalized.endswith(("_mobile", "_phone", "_phone_number", "_telephone")):
        return True

    nearest_context = _nearest_context_kind(contexts)
    key_context = _semantic_kind(normalized)
    person_qualified = key_context == "person"
    business_qualified = key_context == "business"

    if normalized in _PERSON_NAME_KEYS:
        return True
    if normalized == "full_name":
        return nearest_context != "business"
    if normalized == "name":
        return nearest_context == "person"
    if normalized.endswith("_name"):
        if person_qualified:
            return True
        if business_qualified:
            return False
        return nearest_context == "person"

    is_postal_address = normalized in _POSTAL_ADDRESS_KEYS or normalized.endswith(
        _POSTAL_ADDRESS_SUFFIXES
    )
    if normalized in _PERSON_ADDRESS_KEYS or (is_postal_address and person_qualified):
        return True
    if is_postal_address:
        if business_qualified:
            return False
        return nearest_context != "business"
    return normalized in {"contact", "contact_details", "person"}


def _is_recursive_pii_container(key: object, value: object) -> bool:
    if not isinstance(value, (dict, list, tuple)):
        return False
    parts = _normalized_parts(key)
    return bool(parts & (_PERSON_CONTEXT_PARTS | {"address"}))


def _quoted_value_end(message: str, start: int) -> int:
    quote = _QUOTE_ENDS[message[start]]
    index = start + 1
    while index < len(message):
        if message[index] == "\\":
            index += 2
            continue
        if message[index] == quote:
            return index + 1
        index += 1
    return len(message)


def _is_escaped_character(message: str, index: int) -> bool:
    backslashes = 0
    index -= 1
    while index >= 0 and message[index] == "\\":
        backslashes += 1
        index -= 1
    return backslashes % 2 == 1


def _balanced_value_ends(message: str) -> tuple[dict[int, int], int | None]:
    closing = {"(": ")", "[": "]", "{": "}"}
    stack: list[tuple[str, int, bool]] = []
    ends: dict[int, int] = {}
    quote: str | None = None
    quote_start: int | None = None
    structures_seen = 0
    assignment_structures = 0
    index = 0
    while index < len(message):
        character = message[index]
        if quote is not None:
            if character == "\\":
                index += 2
                continue
            if character == quote:
                quote = None
                quote_start = None
        elif character in _QUOTE_SYMBOLS:
            quoted_key = _QUOTED_KEY_CANDIDATE.match(message, index)
            if quoted_key is not None and quoted_key.group("closing") != _QUOTE_ENDS.get(character):
                return ends, index
            if character in _QUOTE_ENDS:
                ordinary_apostrophe = (
                    character == "'"
                    and index > 0
                    and index + 1 < len(message)
                    and message[index - 1].isalnum()
                    and message[index + 1].isalnum()
                )
                if not ordinary_apostrophe and not _is_escaped_character(message, index):
                    quote = _QUOTE_ENDS[character]
                    quote_start = index
        elif character in closing:
            structures_seen += 1
            previous = index - 1
            while previous >= 0 and message[previous].isspace():
                previous -= 1
            follows_assignment = previous >= 0 and message[previous] in ":=：＝"
            if follows_assignment:
                assignment_structures += 1
            if (
                len(stack) >= _MAX_SERIALIZED_DEPTH
                or structures_seen > _MAX_SERIALIZED_STRUCTURES
                or assignment_structures > _MAX_ASSIGNMENTS
            ):
                return ends, stack[0][1] if stack else index
            stack.append((character, index, follows_assignment))
        elif character in closing.values():
            if not stack or closing[stack[-1][0]] != character:
                return ends, stack[0][1] if stack else index
            _opening, start, follows_assignment = stack.pop()
            if follows_assignment:
                ends[start] = index + 1
        index += 1
    if quote_start is not None:
        return ends, quote_start
    if stack:
        if message[stack[-1][1] + 1 :] == _REDACTED:
            return ends, None
        return ends, stack[0][1]
    return ends, None


def _assignment_value_end(
    message: str,
    start: int,
    balanced_ends: dict[int, int],
) -> int:
    if start >= len(message):
        return start
    if message[start] in _QUOTE_ENDS:
        return _quoted_value_end(message, start)
    if message[start] in "([{":
        return balanced_ends.get(start, len(message))

    closing = {"(": ")", "[": "]", "{": "}"}
    stack: list[str] = []
    quote: str | None = None
    index = start
    while index < len(message):
        character = message[index]
        if quote is not None:
            if character == "\\":
                index += 2
                continue
            if character == quote:
                quote = None
            index += 1
            continue
        if character in _QUOTE_ENDS:
            quote = _QUOTE_ENDS[character]
            index += 1
            continue
        if character in closing:
            stack.append(character)
            index += 1
            continue
        if character in closing.values():
            if not stack:
                return index
            if closing[stack[-1]] != character:
                return len(message)
            stack.pop()
            index += 1
            continue
        if stack:
            index += 1
            continue
        if character in ",;":
            next_index = index + 1
            while next_index < len(message) and message[next_index].isspace():
                next_index += 1
            if next_index == len(message) or message[next_index] in "}]":
                return index
            if _ASSIGNMENT_BOUNDARY.match(message, next_index):
                return index
        elif character.isspace():
            next_index = index + 1
            while next_index < len(message) and message[next_index].isspace():
                next_index += 1
            previous_index = index - 1
            while previous_index >= start and message[previous_index].isspace():
                previous_index -= 1
            if (
                previous_index < start or message[previous_index] not in ",;"
            ) and _ASSIGNMENT_BOUNDARY.match(message, next_index):
                return index
            index = next_index
            continue
        index += 1
    return len(message)


def _assignment_key_span(match: re.Match[str]) -> tuple[int, int]:
    for group in ("ascii_key", "smart_single_key", "smart_double_key", "unquoted_key"):
        start = match.start(group)
        if start != -1:
            return start, match.end(group)
    raise AssertionError("assignment matched without a key")


def _normalized_key_path(message: str, start: int, end: int) -> tuple[str, ...] | None:
    parts: list[str] = []
    part_start = start
    for index in range(start, end + 1):
        if index != end and message[index] != ".":
            continue
        if len(parts) == _MAX_SERIALIZED_DEPTH or part_start == index:
            return None
        parts.append(_normalize_key(message[part_start:index]))
        part_start = index + 1
    return tuple(parts)


def _is_sensitive_serialized_key(
    key_path: tuple[str, ...],
    contexts: tuple[str, ...],
) -> bool:
    canonical_key = "_".join(key_path)
    if key_path in _SAFE_BANK_ACCOUNT_DOTTED_PATHS:
        return False
    if len(key_path) > 1 and canonical_key in _SAFE_BANK_ACCOUNT_DIAGNOSTIC_KEYS:
        return True
    if _has_sensitive_key_family(canonical_key):
        return True
    return _is_sensitive_key(key_path[-1], contexts)


def _redact_serialized_assignments(message: str) -> str:
    balanced_ends, malformed_at = _balanced_value_ends(message)
    skip_until = 0
    remaining = _MAX_ASSIGNMENTS
    replacements: list[tuple[int, int, str]] = []
    container_contexts: list[tuple[int, tuple[str, ...]]] = []

    scan_end = malformed_at if malformed_at is not None else len(message)
    for match in _ASSIGNMENT.finditer(message, 0, scan_end):
        if match.start() < skip_until:
            continue
        if remaining == 0:
            replacements.append((match.start(), len(message), _REDACTED))
            break
        container_contexts = [
            container for container in container_contexts if match.start() < container[0]
        ]
        key_start, key_end = _assignment_key_span(match)
        key_path = _normalized_key_path(message, key_start, key_end)
        if key_path is None:
            replacements.append((match.start(), len(message), _REDACTED))
            break
        remaining -= 1
        inherited_contexts = (
            *(part for _end, path in container_contexts for part in path),
            *key_path[:-1],
        )
        value_start = match.end()
        if _is_sensitive_serialized_key(key_path, inherited_contexts):
            value_end = _assignment_value_end(message, value_start, balanced_ends)
            replacements.append((value_start, value_end, _REDACTED))
            skip_until = max(value_end, value_start + 1)
            continue

        if value_start < len(message) and message[value_start] in "([{":
            container_contexts.append((balanced_ends.get(value_start, len(message)), key_path))

    if malformed_at is not None:
        while replacements and replacements[-1][0] >= malformed_at:
            replacements.pop()
        if replacements and replacements[-1][1] > malformed_at:
            start, _end, replacement = replacements[-1]
            replacements[-1] = (start, len(message), replacement)
        else:
            replacements.append((malformed_at, len(message), _REDACTED))

    if not replacements:
        return message
    parts: list[str] = []
    copied_until = 0
    for start, end, replacement in replacements:
        parts.append(message[copied_until:start])
        parts.append(replacement)
        copied_until = end
    parts.append(message[copied_until:])
    return "".join(parts)


def _redact_ip_value(match: re.Match[str]) -> str:
    try:
        ipaddress.ip_address(match.group(0))
    except ValueError:
        return match.group(0)
    return _REDACTED


def redact_log_message(message: str) -> str:
    redacted = _EMAIL_VALUE.sub(_REDACTED, message)
    redacted = _PHONE_VALUE.sub(_REDACTED, redacted)
    redacted = _IPV4_VALUE.sub(_redact_ip_value, redacted)
    redacted = _IPV6_VALUE.sub(_redact_ip_value, redacted)
    return _redact_serialized_assignments(redacted)


class JsonLogFormatter(logging.Formatter):
    def __init__(self, *, service: str, release_revision: str) -> None:
        super().__init__()
        self.service = service
        self.release_revision = release_revision

    def format(self, record: logging.LogRecord) -> str:
        safe_message = scrub_observability_value(record.msg)
        safe_arguments = scrub_observability_value(record.args)
        try:
            message = str(safe_message) % safe_arguments if safe_arguments else str(safe_message)
        except (TypeError, ValueError):
            message = f"{redact_log_message(str(safe_message))} [REDACTED_ARGUMENTS]"
        payload = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "service": self.service,
            "release_revision": self.release_revision,
            "logger": record.name,
            "request_id": get_request_id(),
            "message": redact_log_message(message),
        }
        if record.exc_info:
            payload["exception"] = "[REDACTED_EXCEPTION]"
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def configure_logging(settings: Settings, *, service: str) -> None:
    if settings.log_format != "json":
        return
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    for handler in root.handlers:
        if getattr(handler, "_cardvert_json", False):
            handler.setFormatter(
                JsonLogFormatter(service=service, release_revision=settings.release_revision)
            )
            return
    handler = logging.StreamHandler()
    handler._cardvert_json = True  # type: ignore[attr-defined]
    handler.setFormatter(
        JsonLogFormatter(service=service, release_revision=settings.release_revision)
    )
    root.handlers.clear()
    root.addHandler(handler)


def scrub_observability_value(
    value,
    *,
    semantic_context: object | None = None,
    _contexts: tuple[str, ...] = (),
):
    if semantic_context is not None:
        _contexts = (*_contexts, _normalize_key(semantic_context))
    root: dict[str, object] = {}
    active_containers: set[int] = set()
    visited_nodes = 0
    stack: list[tuple] = [("visit", value, _contexts, 0, root, "value")]

    while stack:
        task = stack.pop()
        if task[0] == "exit":
            _kind, source_id, parent, slot, make_tuple = task
            active_containers.remove(source_id)
            if make_tuple:
                parent[slot] = tuple(parent[slot])
            continue

        _kind, source, contexts, depth, parent, slot = task
        if isinstance(source, str):
            parent[slot] = redact_log_message(source)
            continue
        if not isinstance(source, (dict, list, tuple)):
            parent[slot] = source
            continue

        source_id = id(source)
        visited_nodes += 1
        if (
            source_id in active_containers
            or depth >= _MAX_STRUCTURED_DEPTH
            or visited_nodes > _MAX_STRUCTURED_NODES
        ):
            parent[slot] = _REDACTED
            continue

        active_containers.add(source_id)
        if isinstance(source, dict):
            scrubbed: dict = {key: None for key in source}
            parent[slot] = scrubbed
            stack.append(("exit", source_id, parent, slot, None))
            for key, item in reversed(tuple(source.items())):
                normalized_key = _normalize_key(key)
                child_contexts = (*contexts, normalized_key)
                if _is_recursive_pii_container(key, item):
                    stack.append(("visit", item, child_contexts, depth + 1, scrubbed, key))
                elif _is_sensitive_key(key, contexts):
                    scrubbed[key] = _REDACTED
                else:
                    stack.append(("visit", item, child_contexts, depth + 1, scrubbed, key))
            continue

        scrubbed_items = [None] * len(source)
        parent[slot] = scrubbed_items
        stack.append(("exit", source_id, parent, slot, isinstance(source, tuple)))
        for index in range(len(source) - 1, -1, -1):
            stack.append(("visit", source[index], contexts, depth + 1, scrubbed_items, index))

    return root["value"]


def _before_send(event, _hint):
    return scrub_observability_value(event)


def init_error_tracking(settings: Settings) -> None:
    dsn = settings.sentry_dsn.strip()
    if not dsn:
        return

    sentry_sdk.init(
        dsn=dsn,
        release=settings.release_revision or None,
        traces_sample_rate=0.0,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        before_send=_before_send,
    )


def capture_exception(exc: Exception) -> None:
    sentry_sdk.capture_exception(exc)
