from archapi import ArchAPI
from archapi.planning.task_dag import TaskDAG

print("=== Core flow ===")
engine = ArchAPI("./sample_projects/express_basic")

print("Detection:", engine.detect_framework())
print("Confidence:", engine.compute_confidence())

result = engine.generate_api("Create GET API for user order history", dry_run=True)
print("Generation success:", result.validation_report.success)
print("Generated files:", [str(f.path) for f in result.files])

policy = engine.validate_policy(result)
print("Policy allowed:", policy.allowed)
print("Policy warnings:", policy.warnings)
print("Policy errors:", policy.errors)

print("\n=== Cache ===")
engine.save_cache()
print("Changed files after save:", engine.changed_files())

print("\n=== Security redaction ===")
raw = 'API_KEY="1234567890abcdef"\\nTOKEN="abcdef1234567890"'
print(engine.redact_context(raw))

print("\n=== Secret scan ===")
secret_report = engine.scan_secrets()
print("Secrets clean:", secret_report.success)
for finding in secret_report.findings:
    print(finding)

print("\n=== DAG ===")
dag = TaskDAG.default_api_dag()
print("Ready tasks:", dag.ready_tasks())
dag.mark_completed("detect_models")
dag.mark_completed("detect_route_style")
dag.mark_completed("detect_auth_style")
dag.mark_completed("detect_service_style")
print("Ready after discovery:", dag.ready_tasks())
blocked = dag.mark_failed_and_block_dependents("generate_schema")
print("Blocked after schema failure:", blocked)

print("\n=== Low confidence project ===")
low = ArchAPI(".")
low_plan = low.plan_api("Create GET API for user order history")
print("Low framework:", low.detect_framework())
print("Low confidence:", low.compute_confidence())
print("Low plan generation allowed:", low_plan.generation_allowed)
print("Low plan reason:", low_plan.reason)
