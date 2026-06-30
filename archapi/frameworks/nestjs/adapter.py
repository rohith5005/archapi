from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from archapi.frameworks.generic import GenericAdapter
from archapi.types import APIPlan, APIGenome, GeneratedFile, ScanResult, ValidationReport


class NestJSAdapter(GenericAdapter):
    """
    Framework adapter for NestJS (TypeScript / Node.js).

    Generates decorator-based controller, service, module, DTO, and Jest/spec test
    files that match NestJS conventions.
    """

    name = "nestjs"

    # ------------------------------------------------------------------
    # Scan / genome
    # ------------------------------------------------------------------

    def scan(self, project_path: Path) -> ScanResult:
        result = super().scan(project_path)
        result.framework = self.name
        return result

    def extract_genome(self, maps: Dict[str, Any], scan_result: ScanResult) -> APIGenome:
        genome = super().extract_genome(maps, scan_result)
        genome.framework = self.name

        package_json = scan_result.project_path / "package.json"
        pkg_text = ""
        if package_json.exists():
            pkg_text = package_json.read_text(encoding="utf-8", errors="ignore").lower()

        genome.route_style = "nestjs-controller" if scan_result.routes or scan_result.controllers else "unknown"
        genome.controller_style = "nestjs-controller" if scan_result.controllers else "unknown"
        genome.service_style = "nestjs-service" if scan_result.services else "unknown"
        genome.schema_style = "class-validator" if "class-validator" in pkg_text else (
            "zod" if "zod" in pkg_text else ("dto" if scan_result.schemas else "unknown")
        )
        genome.test_style = "jest" if "jest" in pkg_text else ("spec" if scan_result.tests else "unknown")
        genome.metadata["language"] = "typescript"
        genome.metadata["project_path"] = str(scan_result.project_path)

        has_nestjs = "@nestjs/core" in pkg_text or "@nestjs/common" in pkg_text

        if not scan_result.routes and not scan_result.controllers and not scan_result.services:
            genome.confidence = min(genome.confidence, 0.10)
        elif not has_nestjs:
            genome.confidence = min(genome.confidence, 0.65)
            genome.metadata["package_json_warning"] = "@nestjs/core not found at project root."

        return genome

    # ------------------------------------------------------------------
    # Code generation
    # ------------------------------------------------------------------

    def generate_code(
        self,
        plan: APIPlan,
        genome: APIGenome,
        maps: Dict[str, Any],
    ) -> List[GeneratedFile]:
        if not plan.generation_allowed:
            return []

        entity = plan.entities[-1] if plan.entities else "Resource"
        entity_pascal = entity[0].upper() + entity[1:]
        entity_lower = entity_pascal[0].lower() + entity_pascal[1:]
        entity_file = entity_lower.lower()
        entity_kebab = entity_file.replace("_", "-")

        src_dir = Path("src") / entity_kebab

        controller_path = src_dir / f"{entity_kebab}.controller.ts"
        service_path = src_dir / f"{entity_kebab}.service.ts"
        module_path = src_dir / f"{entity_kebab}.module.ts"
        dto_path = src_dir / f"{entity_kebab}.dto.ts"
        test_path = src_dir / f"{entity_kebab}.controller.spec.ts"

        method = plan.method  # GET / POST / PUT / PATCH / DELETE
        http_path = plan.path
        action = plan.metadata.get("action", "unknown")
        status_code = int(plan.metadata.get("response_status", 200))

        # Map HTTP method to NestJS decorator
        method_decorator_map = {
            "GET": "Get",
            "POST": "Post",
            "PUT": "Put",
            "PATCH": "Patch",
            "DELETE": "Delete",
        }
        nest_decorator = method_decorator_map.get(method, "Get")

        # Strip leading slash for NestJS @Controller + method path
        # e.g. /products/{product_id}/reviews → ["products", "{product_id}", "reviews"]
        path_parts = http_path.lstrip("/").split("/")
        # NestJS uses :param syntax, replace {x} → :x
        nest_path = "/".join(
            part.replace("{", ":").replace("}", "") for part in path_parts
        )

        # ------------------------------------------------------------------
        # controller.ts
        # ------------------------------------------------------------------
        controller_content = f'''import {{ Controller, {nest_decorator}, Body, Param, HttpCode }} from "@nestjs/common";
import {{ {entity_pascal}Service }} from "./{entity_kebab}.service";
import {{ {entity_pascal}Dto }} from "./{entity_kebab}.dto";

@Controller("{nest_path}")
export class {entity_pascal}Controller {{
  constructor(private readonly {entity_lower}Service: {entity_pascal}Service) {{}}

  @{nest_decorator}()
  @HttpCode({status_code})
  async handle(@Body() dto: {entity_pascal}Dto, @Param() params: Record<string, string>) {{
    return this.{entity_lower}Service.execute(dto, params);
  }}
}}
'''

        # ------------------------------------------------------------------
        # service.ts
        # ------------------------------------------------------------------
        service_content = f'''import {{ Injectable }} from "@nestjs/common";
import {{ {entity_pascal}Dto }} from "./{entity_kebab}.dto";

@Injectable()
export class {entity_pascal}Service {{
  async execute(dto: {entity_pascal}Dto, params: Record<string, string>) {{
    // TODO: Replace this placeholder with project-specific business logic.
    return {{
      message: "{entity_pascal} API placeholder response",
      action: "{action}",
      params,
    }};
  }}
}}
'''

        # ------------------------------------------------------------------
        # module.ts
        # ------------------------------------------------------------------
        module_content = f'''import {{ Module }} from "@nestjs/common";
import {{ {entity_pascal}Controller }} from "./{entity_kebab}.controller";
import {{ {entity_pascal}Service }} from "./{entity_kebab}.service";

@Module({{
  controllers: [{entity_pascal}Controller],
  providers: [{entity_pascal}Service],
}})
export class {entity_pascal}Module {{}}
'''

        # ------------------------------------------------------------------
        # dto.ts
        # ------------------------------------------------------------------
        schema_style = genome.schema_style
        if schema_style == "class-validator":
            dto_content = f'''import {{ IsOptional, IsString, IsObject }} from "class-validator";

export class {entity_pascal}Dto {{
  @IsOptional()
  @IsObject()
  payload?: Record<string, unknown>;
}}
'''
        else:
            dto_content = f'''export class {entity_pascal}Dto {{
  payload?: Record<string, unknown>;
}}
'''

        # ------------------------------------------------------------------
        # spec.ts
        # ------------------------------------------------------------------
        test_content = f'''import {{ Test, TestingModule }} from "@nestjs/testing";
import {{ {entity_pascal}Controller }} from "./{entity_kebab}.controller";
import {{ {entity_pascal}Service }} from "./{entity_kebab}.service";

describe("{entity_pascal}Controller", () => {{
  let controller: {entity_pascal}Controller;

  beforeEach(async () => {{
    const module: TestingModule = await Test.createTestingModule({{
      controllers: [{entity_pascal}Controller],
      providers: [{entity_pascal}Service],
    }}).compile();

    controller = module.get<{entity_pascal}Controller>({entity_pascal}Controller);
  }});

  it("should be defined", () => {{
    expect(controller).toBeDefined();
  }});
}});
'''

        return [
            GeneratedFile(controller_path, controller_content),
            GeneratedFile(service_path, service_content),
            GeneratedFile(module_path, module_content),
            GeneratedFile(dto_path, dto_content),
            GeneratedFile(test_path, test_content),
        ]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_generated_code(
        self,
        files: List[GeneratedFile],
        plan: APIPlan,
        genome: APIGenome,
    ) -> ValidationReport:
        errors: List[str] = []
        warnings: List[str] = []

        if not plan.generation_allowed:
            errors.append(plan.reason or "Generation not allowed.")

        required_suffixes = [".controller.ts", ".service.ts", ".module.ts", ".dto.ts"]
        generated_paths = [str(file.path) for file in files]

        for suffix in required_suffixes:
            if not any(path.endswith(suffix) for path in generated_paths):
                errors.append(f"Missing generated NestJS layer: {suffix}")

        if not any(".spec.ts" in path for path in generated_paths):
            errors.append("Missing generated NestJS spec/test layer.")

        for file in files:
            if not file.content.strip():
                errors.append(f"Generated file is empty: {file.path}")
            if Path(file.path).exists():
                warnings.append(
                    f"Generated file path already exists relative to current directory: {file.path}"
                )

        if genome.confidence < 0.75:
            warnings.append("Architecture confidence is moderate; review generated files before applying.")

        return ValidationReport(success=not errors, errors=errors, warnings=warnings)
