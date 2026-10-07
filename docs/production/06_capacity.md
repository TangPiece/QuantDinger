# Capacity

Size targets (strategies, orders/day) should be validated independently for OMS, PostgreSQL, audit, metrics, R2, and workers. Isolate Research workers from Trading workers so heavy Qlib jobs cannot stall OMS.
