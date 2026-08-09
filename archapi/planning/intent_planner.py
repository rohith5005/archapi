from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class IntentPlan:
    method: str
    path: str
    entities: List[str]
    resource: str
    action: str
    response_status: int
    metadata: Dict[str, str] = field(default_factory=dict)


class IntentPlanner:
    EXPLICIT_METHODS = {
        "get": "GET",
        "post": "POST",
        "put": "PUT",
        "patch": "PATCH",
        "delete": "DELETE",
    }

    ENTITY_RULES = [
        ("order", "Order"),
        ("orders", "Order"),
        ("product", "Product"),
        ("products", "Product"),
        ("review", "Review"),
        ("reviews", "Review"),
        ("payment", "Payment"),
        ("payments", "Payment"),
        ("inventory", "Inventory"),
        ("booking", "Booking"),
        ("bookings", "Booking"),
        ("account", "Account"),
        ("accounts", "Account"),
        ("user", "User"),
        ("users", "User"),
        ("profile", "Profile"),
        ("profiles", "Profile"),
    ]

    PLURAL_RULES = {
        "History": "histories",
        "Category": "categories",
        "Company": "companies",
        "Inventory": "inventory",
    }

    def plan(self, request: str) -> IntentPlan:
        text = request.lower()
        method = self._infer_method(text)
        entities = self._infer_entities(text)
        resource = entities[-1] if entities else "Resource"
        action = self._infer_action(text, method)
        path = self._infer_path(text, method, resource)

        return IntentPlan(
            method=method,
            path=path,
            entities=entities,
            resource=resource,
            action=action,
            response_status=self._response_status(method),
            metadata={"planner": "deterministic-v0.2"},
        )

    def _infer_method(self, text: str) -> str:
        for word, method in self.EXPLICIT_METHODS.items():
            if f" {word} " in f" {text} ":
                return method

        if any(word in text for word in ["create", "add", "submit"]):
            return "POST"
        if any(word in text for word in ["update", "edit", "replace"]):
            return "PUT"
        if any(word in text for word in ["modify", "partial"]):
            return "PATCH"
        if any(word in text for word in ["delete", "remove", "disable"]):
            return "DELETE"

        return "GET"

    def _infer_entities(self, text: str) -> List[str]:
        detected: List[str] = []

        for keyword, entity in self.ENTITY_RULES:
            if keyword in text and entity not in detected:
                detected.append(entity)

        if "user" in text and "order" in text:
            return ["User", "Order"]

        if "product" in text and "review" in text:
            return ["Product", "Review"]

        if "product" in text and "inventory" in text:
            return ["Product", "Inventory"]

        if detected:
            return detected[:2]

        return self._infer_entities_generic(text)

    # Words that describe the request itself (HTTP verb, auth/validation
    # qualifiers, generic request/response nouns) rather than the resource
    # being acted on. Kept separate from ENTITY_RULES because this list
    # generalizes to any unlisted resource noun (invoice, shipment,
    # subscription, ticket, comment, ...) instead of requiring every new
    # entity to be hardcoded.
    _GENERIC_STOPWORDS = {
        "create", "creating", "creation", "get", "fetch", "fetching",
        "update", "updating", "delete", "deleting", "remove", "removing",
        "api", "for", "a", "an", "the", "to", "by", "of", "with", "and",
        "or", "via", "using", "history", "status", "new", "existing",
        "details", "detail", "request", "requests", "endpoint",
        "endpoints", "resource", "resources", "submission", "submitting",
        "submit", "authenticated", "unauthenticated", "authorized",
        "unauthorized", "authorization", "authentication", "secure",
        "secured", "public", "private", "validated", "validation",
        "valid", "invalid", "required", "optional",
    }

    def _infer_entities_generic(self, text: str) -> List[str]:
        """
        Fallback resource extraction for nouns not present in ENTITY_RULES.

        Picking the first two leftover content words in sentence order (the
        previous approach) breaks as soon as a qualifier word precedes the
        actual resource -- e.g. "authenticated POST API for refund request"
        would surface "Authenticated"/"Post" instead of "Refund". Natural
        API-request phrasing overwhelmingly follows "... API for <resource>
        ...", so the word immediately after the last "for" is the strongest
        positional signal and is preferred when present.
        """
        words = re.findall(r"[A-Za-z]+", text)
        lowered = [word.lower() for word in words]
        method_words = set(self.EXPLICIT_METHODS.keys())

        content_indices = [
            i for i, word in enumerate(lowered)
            if word not in method_words
            and word not in self._GENERIC_STOPWORDS
            and len(word) > 2
        ]

        if not content_indices:
            return ["Resource"]

        for_index = None
        for i, word in enumerate(lowered):
            if word == "for":
                for_index = i

        if for_index is not None:
            after_for = [i for i in content_indices if i > for_index]
            if after_for:
                primary = after_for[0]
                before_for = [i for i in content_indices if i < for_index]
                ordered = ([before_for[-1]] if before_for else []) + [primary]
                return [words[i].capitalize() for i in ordered][:2]

        return [words[i].capitalize() for i in content_indices[:2]]

    def _infer_action(self, text: str, method: str) -> str:
        if "history" in text:
            return "history"
        if "status" in text:
            return "status"
        if "review" in text:
            return "review"
        if "inventory" in text:
            return "inventory"
        if "disable" in text:
            return "disable"
        if "cancel" in text or "cancellation" in text:
            return "cancellation"

        return {
            "GET": "read",
            "POST": "create",
            "PUT": "update",
            "PATCH": "partial_update",
            "DELETE": "delete",
        }.get(method, "unknown")

    def _infer_path(self, text: str, method: str, resource: str) -> str:
        if "user" in text and "order" in text:
            return "/users/{user_id}/orders"

        if "product" in text and "review" in text:
            if method == "POST":
                return "/products/{product_id}/reviews"
            return "/products/{product_id}/reviews/{id}"

        if "payment" in text and "status" in text:
            return "/payments/{id}/status"

        if "product" in text and "inventory" in text:
            return "/products/{product_id}/inventory"

        if "user" in text and ("disable" in text or method == "DELETE"):
            return "/users/{id}"

        if "booking" in text and ("cancel" in text or "cancellation" in text):
            return "/bookings/{id}/cancellation"

        plural = self.PLURAL_RULES.get(resource, f"{resource.lower()}s")

        if method == "POST":
            return f"/{plural}"

        return f"/{plural}/{{id}}"

    def _response_status(self, method: str) -> int:
        if method == "POST":
            return 201
        return 200
