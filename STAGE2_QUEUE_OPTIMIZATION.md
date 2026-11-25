# QueueFlow AI Stage 2: Smart Counter Allocation and Queue Optimization

The Stage 2 queue helpers are implemented in `queue_optimization.py`.
They calculate student counter workload, recommend the least-loaded compatible
active counter, and schedule waiting student tokens using verified priority,
waiting-time aging, and FIFO rules.

The implementation does not alter the database schema and does not replace the
existing waiting-time service. Visitor tokens use separate `VisitorToken`
records and are not included in student workload or queue calculations.
