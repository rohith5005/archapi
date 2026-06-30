from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from archapi.frameworks.generic import GenericAdapter
from archapi.types import APIPlan, APIGenome, GeneratedFile, ScanResult, ValidationReport


class ExpressTypeScriptAdapter(GenericAdapter):
    name = "express-typescript"

    def scan(self, project_path: Path) -> ScanResult:
        result = super().scan(project_path)
        result.framework = self.name
        return result

    def extract_genome(self, maps: Dict[str, Any], scan_result: ScanResult) -> APIGenome:
        genome = super().extract_genome(maps, scan_result)
        genome.framework = self.name

        package_json = scan_result.project_path / "package.json"
        package_text = ""
        if package_json.exists():
            package_text = package_json.read_text(
                encoding="utf-8",
                errors="ignore",
            ).lower()

        if "zod" in package_text:
            genome.schema_style = "zod"
        elif "joi" in package_text:
            genome.schema_style = "joi"

        if "jest" in package_text and "supertest" in package_text:
            genome.test_style = "jest-supertest"

        genome.route_style = "express-router" if scan_result.routes else "unknown"
        genome.controller_style = "express-controller" if scan_result.controllers else "unknown"
        genome.service_style = "service-layer" if scan_result.services else "unknown"
        genome.metadata["language"] = "typescript"
        genome.metadata["project_path"] = str(scan_result.project_path)

        required_layers = [
            bool(scan_result.routes),
            bool(scan_result.controllers),
            bool(scan_result.services),
        ]

        has_express_package = "express" in package_text

        if not any(required_layers):
            genome.confidence = min(genome.confidence, 0.10)
        elif not has_express_package:
            # If route/controller/service layers are present but package.json is missing
            # at project root, allow generation with warning-level confidence.
            # This supports config-hint mode for monorepos or unusual layouts.
            genome.confidence = min(genome.confidence, 0.65)
            genome.metadata["package_json_warning"] = "Express package.json not found at project root."

        return genome

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

        route_dir = self._output_dir(maps, "route_map", "src/routes")
        controller_dir = self._output_dir(maps, "controller_map", "src/controllers")
        service_dir = self._output_dir(maps, "service_map", "src/services")
        schema_dir = self._output_dir(maps, "schema_map", "src/schemas")
        test_dir = self._output_dir(maps, "test_map", "tests")

        route_path = route_dir / f"{entity_file}.routes.ts"
        controller_path = controller_dir / f"{entity_file}.controller.ts"
        service_path = service_dir / f"{entity_file}.service.ts"
        schema_path = schema_dir / f"{entity_file}.schema.ts"
        test_path = test_dir / f"{entity_file}.test.ts"

        express_path = (
            plan.path
            .replace("{user_id}", ":userId")
            .replace("{product_id}", ":productId")
            .replace("{id}", ":id")
        )

        status_code = int(plan.metadata.get("response_status", 200))
        action = plan.metadata.get("action", "unknown")

        route_content = f"""import {{ Router, Request, Response, NextFunction }} from "express";
import {{ {entity_lower}Controller }} from "../controllers/{entity_file}.controller";
import {{ {entity_lower}RequestSchema }} from "../schemas/{entity_file}.schema";

const router = Router();

function validate{entity_pascal}Request(req: Request, res: Response, next: NextFunction) {{
  const parsed = {entity_lower}RequestSchema.safeParse({{
    params: req.params,
    query: req.query,
    body: req.body,
  }});

  if (!parsed.success) {{
    return res.status(400).json({{ errors: parsed.error.flatten() }});
  }}

  return next();
}}

router.{plan.method.lower()}("{express_path}", validate{entity_pascal}Request, {entity_lower}Controller.handle);

export default router;
"""

        controller_content = f"""import {{ Request, Response, NextFunction }} from "express";
import {{ {entity_lower}Service }} from "../services/{entity_file}.service";

export const {entity_lower}Controller = {{
  async handle(req: Request, res: Response, next: NextFunction) {{
    try {{
      const result = await {entity_lower}Service.execute({{
        params: req.params,
        query: req.query,
        body: req.body,
      }});

      return res.status({status_code}).json({{ data: result }});
    }} catch (error) {{
      return next(error);
    }}
  }},
}};
"""

        service_content = f"""type {entity_pascal}ServiceInput = {{
  params: Record<string, unknown>;
  query: Record<string, unknown>;
  body: unknown;
}};

export const {entity_lower}Service = {{
  async execute(input: {entity_pascal}ServiceInput) {{
    // TODO: Replace this placeholder with project-specific business logic.
    return {{
      message: "{entity_pascal} API placeholder response",
      action: "{action}",
      params: input.params,
      query: input.query,
      body: input.body,
    }};
  }},
}};
"""

        schema_content = f"""import {{ z }} from "zod";

export const {entity_lower}RequestSchema = z.object({{
  params: z.record(z.unknown()).optional(),
  query: z.record(z.unknown()).optional(),
  body: z.unknown().optional(),
}});

export type {entity_pascal}Request = z.infer<typeof {entity_lower}RequestSchema>;
"""

        test_content = f"""describe("{entity_pascal} API", () => {{
  it("should have a generated placeholder test", () => {{
    // TODO: Replace this placeholder with a real Supertest request.
    expect(true).toBe(true);
  }});
}});
"""

        return [
            GeneratedFile(route_path, route_content),
            GeneratedFile(controller_path, controller_content),
            GeneratedFile(service_path, service_content),
            GeneratedFile(schema_path, schema_content),
            GeneratedFile(test_path, test_content),
        ]

    def _output_dir(self, maps: Dict[str, Any], map_key: str, fallback: str) -> Path:
        values = maps.get(map_key, {})
        project_path = Path(maps.get("_project_path", "."))

        if isinstance(values, dict) and values:
            first_path = Path(next(iter(values.values()))).resolve()
            parent = first_path.parent

            try:
                return parent.relative_to(project_path)
            except ValueError:
                return Path(fallback)

        return Path(fallback)

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

        required_layers = ["routes", "controllers", "services", "schemas", "tests"]
        generated_paths = [str(file.path) for file in files]

        for layer in required_layers:
            if not any(layer in path for path in generated_paths):
                errors.append(f"Missing generated {layer} layer.")

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
