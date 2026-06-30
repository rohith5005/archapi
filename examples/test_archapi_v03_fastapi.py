from archapi import ArchAPI


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


print("=== Phase 3 FastAPI Adapter Test ===")

engine = ArchAPI("./sample_projects/fastapi_basic")

detection = engine.detect_framework()
confidence = engine.compute_confidence()

print("Detection:", detection)
print("Confidence:", confidence)

assert_true(detection.framework == "fastapi", "Expected FastAPI detection")
assert_true(confidence["mode"] in {"generate", "generate_with_warnings"}, "Expected generation-capable mode")

requests = [
    ("Create GET API for user order history", "GET", "/users/{user_id}/orders"),
    ("Create POST API for product review", "POST", "/products/{product_id}/reviews"),
    ("Create GET API for payment status", "GET", "/payments/{id}/status"),
]

for request, expected_method, expected_path in requests:
    print("\nRequest:", request)

    result = engine.generate_api(request, dry_run=True)
    score = engine.score_architecture(result)

    print("Plan:", result.plan)
    print("Files:", [str(f.path) for f in result.files])
    print("Validation:", result.validation_report)
    print("Architecture score:", score.percentage)

    assert_true(result.plan.method == expected_method, f"Expected method {expected_method}")
    assert_true(result.plan.path == expected_path, f"Expected path {expected_path}")
    assert_true(result.validation_report.success, "Expected FastAPI generation validation success")
    assert_true(len(result.files) == 4, "Expected 4 generated files")
    assert_true(score.percentage == 100.0, "Expected 100 FastAPI architecture score")

    print("Router:")
    print(result.files[0].content)


print("\n=== Strict FastAPI config mode ===")

configured = ArchAPI(
    ".",
    framework="fastapi",
    config={
        "route_dir": "sample_projects/fastapi_basic/app/routers",
        "service_dir": "sample_projects/fastapi_basic/app/services",
        "schema_dir": "sample_projects/fastapi_basic/app/schemas",
        "test_dir": "sample_projects/fastapi_basic/tests",
    },
)

scan = configured.scan()
configured_result = configured.generate_api("Create POST API for product review", dry_run=True)
configured_score = configured.score_architecture(configured_result)

print("Unknown count:", len(scan.unknown))
print("Configured files:", [str(f.path) for f in configured_result.files])
print("Validation:", configured_result.validation_report)
print("Architecture score:", configured_score.percentage)

assert_true(len(scan.unknown) == 0, "Strict FastAPI config mode should not scan unrelated files")
assert_true(configured_result.validation_report.success, "Configured FastAPI generation should pass")
assert_true(configured_score.percentage == 100.0, "Configured FastAPI architecture score should be 100")

print("\nPhase 3 FastAPI adapter passed")
