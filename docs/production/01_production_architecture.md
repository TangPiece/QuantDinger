# Production Architecture

Research Plane (Qlib, Factor Lab, R2 datasets) feeds **Domain Contracts** (Signal, TargetPosition). Trading Plane (Risk, OMS, Safety, Broker, Reconciliation, Ops) executes orders. Planes must not share execution paths: research workers must not starve OMS.
