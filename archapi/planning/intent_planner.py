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

        words = re.findall(r"[A-Za-z]+", text)
        stop = {
            "create", "get", "fetch", "update", "delete", "api", "for",
            "a", "an", "the", "to", "by", "of", "history", "status",
            "new", "existing", "details", "detail"
        }

        fallback = []
        for word in words:
            if word.lower() not in stop and len(word) > 2:
                fallback.append(word.capitalize())

        return fallback[:2] or ["Resource"]

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
