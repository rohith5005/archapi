from __future__ import annotations

from archapi.frameworks.generic import GenericAdapter
from archapi.frameworks.express_ts.adapter import ExpressTypeScriptAdapter
from archapi.frameworks.fastapi_adapter import FastAPIAdapter
from archapi.frameworks.django_drf_adapter import DjangoRestFrameworkAdapter


class FrameworkRegistry:
    def __init__(self) -> None:
        generic = GenericAdapter()

        self._adapters = {
            "generic": generic,
            "express-typescript": ExpressTypeScriptAdapter(),
            "nestjs": generic,
            "fastapi": FastAPIAdapter(),
            "django-drf": DjangoRestFrameworkAdapter(),
            "flask": generic,
            "spring-boot": generic,
            "dotnet-core": generic,
            "laravel": generic,
            "rails": generic,
            "go-api": generic,
            "node-unknown": generic,
        }

    def get(self, framework: str):
        return self._adapters.get(framework, self._adapters["generic"])
