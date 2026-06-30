from archapi import ArchAPI

engine = ArchAPI("./sample_projects/express_basic")

print("DETECTION")
print(engine.detect_framework())

print("\nSCAN")
scan = engine.scan()
print(scan)

print("\nMAPS")
maps = engine.build_maps()
print(maps)

print("\nGENOME")
genome = engine.extract_genome()
print(genome)

print("\nCONFIDENCE")
print(engine.compute_confidence())

print("\nPLAN")
plan = engine.plan_api("Create GET API for user order history")
print(plan)

print("\nGENERATION")
result = engine.generate_api("Create GET API for user order history", dry_run=True)
print(result.plan)
print(result.validation_report)
print("Generated files:", [str(f.path) for f in result.files])

print("\nDIFF")
print(result.diff)
