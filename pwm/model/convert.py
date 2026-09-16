"""Checkpoint keys → ``NanoMoT`` state-dict keys.

Two on-disk layouts carry the same tensors (identical shapes, no reshapes):

* **diffusers** — ``nvidia/Cosmos3-Nano`` ``transformer/`` (``layers.N.self_attn.to_q.weight`` ...); the
  layout ``pwm`` loads, trains from and writes (``consolidate``).
* **training** — the flat ``model-*.safetensors`` a Cosmos fine-tune saves and ``Hokin/PWM-WROP`` ships
  (``language_model.model.layers.N.self_attn.q_proj_moe_gen.weight`` ...). :func:`training_key_to_diffusers`
  renames it into the first; ``pwm.model.load.read_index`` applies it when it finds a root
  ``model.safetensors.index.json`` instead of a ``transformer/`` folder.

A pure key map (regex + dict), no model instantiation, that **raises on any key it does not
recognise** so an upstream layout drift fails loudly. Keys the video model does not use are listed
explicitly in ``DROPPED_PREFIXES`` and skipped.

814 checkpoint keys = 36 layers × 22 + 22 non-layer. Per layer (diffusers → pwm):

    self_attn.to_q/to_k/to_v/to_out      → blocks.{i}.und.q/k/v/o
    self_attn.norm_q/norm_k              → blocks.{i}.und.q_norm/k_norm
    self_attn.add_q_proj/add_k_proj/add_v_proj/to_add_out → blocks.{i}.gen.q/k/v/o
    self_attn.norm_added_q/norm_added_k  → blocks.{i}.gen.q_norm/k_norm
    mlp.gate_proj/up_proj/down_proj      → blocks.{i}.und.mlp.gate/up/down
    mlp_moe_gen.*                        → blocks.{i}.gen.mlp.*
    input_layernorm(_moe_gen)            → blocks.{i}.und|gen.norm1
    post_attention_layernorm(_moe_gen)   → blocks.{i}.und|gen.norm2

Non-layer: ``embed_tokens`` → ``embed``, ``norm_moe_gen`` → ``norm_gen``, ``proj_in`` → ``vae2llm``,
``proj_out`` → ``llm2vae``, ``time_embedder.linear_1/2`` → ``time_embedder.0/2``.
Dropped: ``lm_head``, ``norm`` (und final norm; text-prediction only), ``action_*``, ``audio_*``.

All tensors map 1:1 with no reshapes (Linear→Linear, same head order), so the converter is a
rename; sharding happens later in ``pwm/model/load.py`` per DTensor placement.
"""

from __future__ import annotations

import re

__all__ = ["DROPPED_PREFIXES", "map_key", "map_state_dict_keys", "pwm_key_to_diffusers", "training_key_to_diffusers"]

DROPPED_PREFIXES = ("lm_head.", "norm.", "action_", "audio_")

_NONLAYER = {
    "embed_tokens.weight": "embed.weight",
    "norm_moe_gen.weight": "norm_gen.weight",
    "proj_in.weight": "vae2llm.weight",
    "proj_in.bias": "vae2llm.bias",
    "proj_out.weight": "llm2vae.weight",
    "proj_out.bias": "llm2vae.bias",
    "time_embedder.linear_1.weight": "time_embedder.0.weight",
    "time_embedder.linear_1.bias": "time_embedder.0.bias",
    "time_embedder.linear_2.weight": "time_embedder.2.weight",
    "time_embedder.linear_2.bias": "time_embedder.2.bias",
}

_LAYER = {
    "self_attn.to_q": "und.q",
    "self_attn.to_k": "und.k",
    "self_attn.to_v": "und.v",
    "self_attn.to_out": "und.o",
    "self_attn.norm_q": "und.q_norm",
    "self_attn.norm_k": "und.k_norm",
    "self_attn.add_q_proj": "gen.q",
    "self_attn.add_k_proj": "gen.k",
    "self_attn.add_v_proj": "gen.v",
    "self_attn.to_add_out": "gen.o",
    "self_attn.norm_added_q": "gen.q_norm",
    "self_attn.norm_added_k": "gen.k_norm",
    "mlp.gate_proj": "und.mlp.gate",
    "mlp.up_proj": "und.mlp.up",
    "mlp.down_proj": "und.mlp.down",
    "mlp_moe_gen.gate_proj": "gen.mlp.gate",
    "mlp_moe_gen.up_proj": "gen.mlp.up",
    "mlp_moe_gen.down_proj": "gen.mlp.down",
    "input_layernorm": "und.norm1",
    "input_layernorm_moe_gen": "gen.norm1",
    "post_attention_layernorm": "und.norm2",
    "post_attention_layernorm_moe_gen": "gen.norm2",
}

_LAYER_RE = re.compile(r"^layers\.(\d+)\.(.+)\.weight$")

# training layout → diffusers layout (non-layer keys and the per-layer attention names; everything else is
# identical once the ``language_model.model.`` / ``language_model.`` prefix is gone)
_TRAIN_NONLAYER = {
    "language_model.lm_head.weight": "lm_head.weight",
    "language_model.model.embed_tokens.weight": "embed_tokens.weight",
    "language_model.model.norm.weight": "norm.weight",
    "language_model.model.norm_moe_gen.weight": "norm_moe_gen.weight",
    "vae2llm.weight": "proj_in.weight",
    "vae2llm.bias": "proj_in.bias",
    "llm2vae.weight": "proj_out.weight",
    "llm2vae.bias": "proj_out.bias",
    "time_embedder.mlp.0.weight": "time_embedder.linear_1.weight",
    "time_embedder.mlp.0.bias": "time_embedder.linear_1.bias",
    "time_embedder.mlp.2.weight": "time_embedder.linear_2.weight",
    "time_embedder.mlp.2.bias": "time_embedder.linear_2.bias",
}
_TRAIN_ATTN = {
    "q_proj": "to_q",
    "k_proj": "to_k",
    "v_proj": "to_v",
    "o_proj": "to_out",
    "q_norm": "norm_q",
    "k_norm": "norm_k",
    "q_proj_moe_gen": "add_q_proj",
    "k_proj_moe_gen": "add_k_proj",
    "v_proj_moe_gen": "add_v_proj",
    "o_proj_moe_gen": "to_add_out",
    "q_norm_moe_gen": "norm_added_q",
    "k_norm_moe_gen": "norm_added_k",
}
_TRAIN_LAYER_RE = re.compile(r"^language_model\.model\.layers\.(\d+)\.(.+)\.weight$")


def training_key_to_diffusers(key: str) -> str:
    """Training-layout key (``Hokin/PWM-WROP``) → diffusers-layout key. Raises on unknown keys."""
    if key in _TRAIN_NONLAYER:
        return _TRAIN_NONLAYER[key]
    m = _TRAIN_LAYER_RE.match(key)
    if m:
        i, rest = int(m.group(1)), m.group(2)
        if rest.startswith("self_attn."):
            name = rest[len("self_attn.") :]
            if name not in _TRAIN_ATTN:
                raise KeyError(f"unrecognised training checkpoint key: {key!r}")
            rest = "self_attn." + _TRAIN_ATTN[name]
        return f"layers.{i}.{rest}.weight"
    raise KeyError(f"unrecognised training checkpoint key: {key!r}")


def map_key(key: str) -> str | None:
    """Diffusers key → pwm key, or ``None`` if the key is deliberately dropped. Raises on unknown keys."""
    if key.startswith(DROPPED_PREFIXES):
        return None
    if key in _NONLAYER:
        return _NONLAYER[key]
    m = _LAYER_RE.match(key)
    if m and m.group(2) in _LAYER:
        return f"blocks.{int(m.group(1))}.{_LAYER[m.group(2)]}.weight"
    raise KeyError(f"unrecognised Cosmos3-Nano checkpoint key: {key!r}")


def map_state_dict_keys(keys, layers: int | None = None) -> dict[str, str]:
    """``{diffusers_key: pwm_key}`` for every kept key (optionally only ``layers`` < N)."""
    out: dict[str, str] = {}
    for k in keys:
        pk = map_key(k)
        if pk is None:
            continue
        if layers is not None and pk.startswith("blocks.") and int(pk.split(".")[1]) >= layers:
            continue
        out[k] = pk
    return out


def pwm_key_to_diffusers(layers: int = 36) -> dict[str, str]:
    """Inverse map for every pwm key of an ``layers``-deep model (used to load and to compare grads)."""
    inv = {v: k for k, v in _NONLAYER.items()}
    for i in range(layers):
        for dk, pk in _LAYER.items():
            inv[f"blocks.{i}.{pk}.weight"] = f"layers.{i}.{dk}.weight"
    return inv


if __name__ == "__main__":
    assert map_key("layers.3.self_attn.add_k_proj.weight") == "blocks.3.gen.k.weight"
    assert map_key("layers.0.mlp_moe_gen.down_proj.weight") == "blocks.0.gen.mlp.down.weight"
    assert map_key("lm_head.weight") is None and map_key("norm.weight") is None
    assert map_key("action_proj_in.fc.weight") is None and map_key("audio_modality_embed") is None
    try:
        map_key("layers.0.self_attn.something.weight")
        raise AssertionError("unknown key must raise")
    except KeyError:
        pass
    inv = pwm_key_to_diffusers(2)
    assert (
        len(inv) == 10 + 22 * 2
        and inv["blocks.1.und.norm2.weight"] == "layers.1.post_attention_layernorm.weight"
    )
    # training layout: every key of the 804-tensor PWM-WROP checkpoint lands on a diffusers key, and every
    # pwm parameter has a training-layout source
    t2d = training_key_to_diffusers
    assert t2d("language_model.model.layers.3.self_attn.k_proj_moe_gen.weight") == "layers.3.self_attn.add_k_proj.weight"
    assert t2d("language_model.model.layers.0.self_attn.o_proj.weight") == "layers.0.self_attn.to_out.weight"
    assert t2d("language_model.model.layers.0.mlp_moe_gen.up_proj.weight") == "layers.0.mlp_moe_gen.up_proj.weight"
    assert t2d("time_embedder.mlp.2.bias") == "time_embedder.linear_2.bias" and t2d("vae2llm.weight") == "proj_in.weight"
    assert map_key(t2d("language_model.lm_head.weight")) is None
    try:
        t2d("language_model.model.layers.0.self_attn.qkv.weight")
        raise AssertionError("unknown training key must raise")
    except KeyError:
        pass
    train_keys = list(_TRAIN_NONLAYER) + [
        f"language_model.model.layers.{i}.{r}.weight"
        for i in range(36)
        for r in [f"self_attn.{a}" for a in _TRAIN_ATTN]
        + ["mlp.gate_proj", "mlp.up_proj", "mlp.down_proj", "mlp_moe_gen.gate_proj", "mlp_moe_gen.up_proj",
           "mlp_moe_gen.down_proj", "input_layernorm", "input_layernorm_moe_gen", "post_attention_layernorm",
           "post_attention_layernorm_moe_gen"]
    ]
    assert len(train_keys) == 804
    covered = {t2d(k) for k in train_keys}
    assert set(pwm_key_to_diffusers(36).values()) <= covered
    print("convert smoke OK")
