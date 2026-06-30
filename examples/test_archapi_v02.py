from archapi import ArchAPI


REQUESTS = [
    "Create GET API for user order history",
    "Create POST API for product review",
    "Create GET API for payment status",
    "Create DELETE API for user account",
    "Create PUT API to update product inventory",
    "Create GET API for booking cancellation history",
]


def run_case(request: str) -> None:
    engine = ArchAPI("./sample_projects/express_basic")
    result = engine.generate_api(request, dry_run=True)
    score = engine.score_architecture(result)

    print("\nREQUEST:", request)
    print("PLAN:", result.plan)
    print("VALID:", result.validation_report.success)
    print("WARNINGS:", result.validation_report.warnings)
    print("FILES:", [str(f.path) for f in result.files])
    print("ARCH_SCORE:", score.percentage)

    if result.files:
        print("ROUTE:")
        print(result.files[0].content)


for req in REQUESTS:
    run_case(req)


print("\nLOW CONFIDENCE CHECK")
low = ArchAPI(".")
plan = low.plan_api("Create GET API for user order history")
print(low.detect_framework())
print(low.compute_confidence())
print("allowed:", plan.generation_allowed)
print("reason:", plan.reason)


print("\nSTRICT CONFIG CHECK")
configured = ArchAPI(
    ".",
    framework="express-typescript",
    config={
        "route_dir": "sample_projects/express_basic/src/routes",
        "controller_dir": "sample_projects/express_basic/src/controllers",
        "service_dir": "sample_projects/express_basic/src/services",
        "model_dir": "sample_projects/express_basic/src/models",
        "schema_dir": "sample_projects/express_basic/src/schemas",
        "middleware_dir": "sample_projects/express_basic/src/middleware",
        "test_dir": "sample_projects/express_basic/tests",
    },
)
scan = configured.scan()
print("unknown_count:", len(scan.unknown))
configured_result = configured.generate_api("Create POST API for product review", dry_run=True)
print("configured_valid:", configured_result.validation_report.success)
print("configured_files:", [str(f.path) for f in configured_result.files])
if configured_result.files:
    print(configured_result.files[0].content)
else:
    print("No configured files generated.")
    print(configured_result.validation_report)
