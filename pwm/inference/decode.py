"""Wan2.2 VAE decode on CPU: normalised latent ``[1,48,T,H/16,W/16]`` → pixels → mp4.

The network works in the tokenizer's **normalised** latent space (``z_norm = (z - mean) / std``); the
diffusers ``AutoencoderKLWan`` decoder wants the raw latent, so ``z = z_norm * std + mean``
(``latents_mean/std`` from ``vae/config.json``, identical to upstream ``WanVAE.scale``). Runs in a
pure-CPU process (``TORCH_DEVICE_BACKEND_AUTOLOAD=0``). torchvision is never used (ABI-incompatible
with the Neuron torch): frames go through imageio.
"""

from __future__ import annotations

import os

import numpy as np
import torch

__all__ = ["load_vae", "latent_stats", "decode_latent", "to_uint8_frames", "write_mp4"]


def load_vae(vae_dir: str):
    from diffusers import AutoencoderKLWan  # noqa: PLC0415

    return AutoencoderKLWan.from_pretrained(vae_dir, torch_dtype=torch.float32).eval()


def latent_stats(vae) -> tuple[torch.Tensor, torch.Tensor]:
    c = vae.config
    mean = torch.tensor(c.latents_mean, dtype=torch.float32).view(1, c.z_dim, 1, 1, 1)
    std = torch.tensor(c.latents_std, dtype=torch.float32).view(1, c.z_dim, 1, 1, 1)
    return mean, std


@torch.no_grad()
def decode_latent(latent_norm: torch.Tensor, vae) -> torch.Tensor:
    """``[1,48,T,h,w]`` normalised → ``[1,3,4(T-1)+1,16h,16w]`` pixels in ``[-1, 1]``."""
    mean, std = latent_stats(vae)
    assert latent_norm.shape[1] == vae.config.z_dim, latent_norm.shape
    z = latent_norm.to(torch.float32) * std + mean
    return vae.decode(z, return_dict=False)[0]


def to_uint8_frames(pixels: torch.Tensor) -> np.ndarray:
    v = pixels[0].clamp(-1, 1)
    v = ((v + 1.0) / 2.0 * 255.0).round().to(torch.uint8)
    return v.permute(1, 2, 3, 0).contiguous().cpu().numpy()  # [T,H,W,3]


def write_mp4(frames: np.ndarray, out_path: str, fps: float) -> None:
    import imageio.v2 as imageio  # noqa: PLC0415

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with imageio.get_writer(
        out_path, format="FFMPEG", mode="I", fps=fps, codec="libx264", quality=8, macro_block_size=1
    ) as w:
        for f in frames:
            w.append_data(f)


if __name__ == "__main__":
    # Hardware-free smoke (no VAE): pixel → uint8 frame conversion clamps, rounds and lays out [T,H,W,3].
    px = torch.tensor([-2.0, -1.0, 0.0, 1.0, 2.0]).reshape(1, 1, 5, 1, 1).expand(1, 3, 5, 2, 2)
    fr = to_uint8_frames(px)
    assert fr.shape == (5, 2, 2, 3) and fr.dtype == np.uint8
    assert fr[:, 0, 0, 0].tolist() == [0, 0, 128, 255, 255], fr[:, 0, 0, 0]
    print("decode smoke OK")
