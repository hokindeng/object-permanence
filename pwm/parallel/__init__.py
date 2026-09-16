"""Parallelism for ``NanoMoT`` — TP (weights) × FSDP2 (params/grads/optimizer state) on a 2-D
``("dp", "tp")`` mesh. Native ``torch.distributed`` + DTensor; no torch-xla, no neuronx_distributed.

Modules:
  mesh  — process group (gloo / "neuron"), ``build_mesh(fsdp, tp)``.
  tp    — ``parallelize``: Colwise q/k/v/gate/up + Rowwise o/down per tower, head patch;
          ``reduce_tp_partial_grads`` (q/k-norm gains), ``sync_tp_replicated_grads``.
  fsdp  — ``apply_fsdp2`` (blocks + fp32 island + root), ``fsdp2_mp_policy``, ``compile_blocks``.
  grad  — ``clip_grad_norm`` from local shards (the trainer's clip).

``pwm.cli.build_model`` is the one place that composes them (mesh → TP → sharded load → FSDP2 → prefetch
→ compile). Training-step contract:
``backward → reduce_tp_partial_grads → sync_tp_replicated_grads → clip_grad_norm → step``.
"""
