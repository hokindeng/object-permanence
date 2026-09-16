"""Model core: the Cosmos3-Nano MoT forward path, flat and static-shape. Every module is hardware-free
and carries a ``__main__`` smoke.

- ``rope``        interleaved 3-D mRoPE (cos/sin built on CPU) and the out-of-place rotate-half apply
- ``patchify``    latent ⇄ 192-dim patch tokens, per-token noisy mask
- ``diffusion``   rectified-flow sigma sampling, noise, velocity target, loss, timestep sinusoid
- ``attention``   two-way attention (text causal, vision full), GQA; explicit-fp32 and NKI paths
- ``block``       RMSNorm, SwiGLU, Tower (und | gen), MoTBlock
- ``mot``         NanoMoT: embed → vae2llm (+ timestep) → blocks → norm_gen → llm2vae
- ``convert``     diffusers checkpoint keys ↔ pwm keys (raises on unknown keys)
- ``load``        meta-init → per-rank sharded safetensors streaming
- ``consolidate`` per-rank training shards → one diffusers-layout checkpoint
"""
