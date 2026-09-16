"""Training: ``train.fit`` (the one loop: accumulation, TP partial-grad sum, clip from local shards,
all-reduce-MIN skip guard, atomic per-rank checkpoints with bit-exact resume)."""
