"""Encoded-clip dataset and a seeded, DP-partitioned, resumable sampler.

On disk (written by ``pwm/data/encode.py``): one ``<id>.pt`` per clip, a dict ``{"latent": Float[1,48,T,H,W]
(normalised Wan2.2 VAE latent), "text_ids": Long[Lt], "cond_latent_frames": int, "caption": str, "src": str,
"fps": float, "real_px_frames": int}``. Every clip in a run has the same ``T, H, W, Lt`` (one compiled shape).
With ``expect`` (the YAML ``data:`` geometry — what ``fit`` passes) every file is checked at construction, by
mmap, so a wrong clips_dir fails before the first step instead of at the step that happens to draw the odd clip;
without it the first item read sets the run shape and every later item is checked against it. Sampler: one
seeded permutation per epoch, rank ``dp_rank`` takes every ``dp_world``-th index; ``state_dict`` carries the
cursor so a resume replays the identical order.
"""

from __future__ import annotations

from pathlib import Path

import torch

from pwm.model.patchify import LATENT_CHANNELS

__all__ = ["ClipDataset", "ResumableSampler"]


def _shape_of(d: dict) -> tuple:
    return tuple(d["latent"].shape), int(d["text_ids"].shape[0]), int(d.get("cond_latent_frames", 0))


class ClipDataset:
    def __init__(self, clips_dir: str | Path, *, expect: dict | None = None):
        self.root = Path(clips_dir)
        self.files = sorted(self.root.glob("*.pt"))
        if not self.files:
            raise FileNotFoundError(f"no clips under {self.root}")
        self._shape: tuple | None = None
        if expect is not None:
            self._scan(expect)

    def _scan(self, e: dict) -> None:
        """``e`` = ``asdict(DataConfig)``-like: latent_t, height, width, text_len, cond_latent_frames."""
        want = (
            (1, LATENT_CHANNELS, int(e["latent_t"]), int(e["height"]) // 16, int(e["width"]) // 16),
            int(e["text_len"]),
            int(e["cond_latent_frames"]),
        )
        bad = []
        for f in self.files:
            try:
                s = _shape_of(torch.load(f, map_location="cpu", weights_only=False, mmap=True))
            except Exception as exc:  # unreadable file is as fatal as a wrong one
                bad.append(f"{f.name}: {type(exc).__name__}: {exc}")
                continue
            if s != want:
                bad.append(f"{f.name}: {s}")
        if bad:
            head = "\n  ".join(bad[:10]) + (f"\n  ... {len(bad) - 10} more" if len(bad) > 10 else "")
            raise ValueError(
                f"{self.root}: {len(bad)}/{len(self.files)} clips do not match the YAML data geometry "
                f"(latent, text_len, cond_latent_frames) = {want}:\n  {head}"
            )
        self._shape = want

    def __len__(self) -> int:
        return len(self.files)

    def __getitem__(self, i: int) -> dict:
        d = torch.load(self.files[i], map_location="cpu", weights_only=False)
        shape = _shape_of(d)
        if self._shape is None:
            self._shape = shape
        elif shape != self._shape:
            raise ValueError(
                f"{self.files[i]}: shape {shape} != run shape {self._shape} (one NEFF shape per run)"
            )
        return d


class ResumableSampler:
    """Seeded epoch permutations, DP-partitioned, with a cursor for bit-exact resume."""

    def __init__(self, n: int, dp_rank: int = 0, dp_world: int = 1, seed: int = 0):
        assert 0 <= dp_rank < dp_world and n > 0
        assert n >= dp_world, (
            f"ResumableSampler: {n} clips < dp_world={dp_world} — every DP rank needs its own index "
            f"per step (rank r reads position cursor+r); add clips or lower fsdp"
        )
        self.n, self.dp_rank, self.dp_world, self.seed = n, dp_rank, dp_world, seed
        self.epoch = 0
        self.cursor = 0  # position within the current epoch's *global* permutation

    def _perm(self) -> torch.Tensor:
        g = torch.Generator().manual_seed(self.seed * 1_000_003 + self.epoch)
        return torch.randperm(self.n, generator=g)

    def next_index(self) -> int:
        """Global step semantics: consecutive calls on rank r return this rank's share of the permutation."""
        perm = self._perm()
        pos = self.cursor + self.dp_rank
        if pos >= self.n:
            self.epoch += 1
            self.cursor = 0
            perm = self._perm()
            pos = self.dp_rank
        idx = int(perm[pos])
        self.cursor += self.dp_world
        return idx

    def state_dict(self) -> dict:
        return {"epoch": self.epoch, "cursor": self.cursor, "seed": self.seed, "n": self.n}

    def load_state_dict(self, sd: dict) -> None:
        assert sd["n"] == self.n and sd["seed"] == self.seed, (
            "sampler state does not match this dataset/seed"
        )
        self.epoch, self.cursor = int(sd["epoch"]), int(sd["cursor"])


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        for i in range(5):
            torch.save(
                {
                    "latent": torch.randn(1, 4, 2, 4, 6),
                    "text_ids": torch.arange(7),
                    "cond_latent_frames": 0,
                    "caption": f"c{i}",
                    "src": f"v{i}.mp4",
                    "fps": 24.0,
                },
                Path(td) / f"clip{i}.pt",
            )
        ds = ClipDataset(td)
        assert len(ds) == 5 and ds[0]["latent"].shape == (1, 4, 2, 4, 6)
        geom = {"latent_t": 2, "height": 64, "width": 96, "text_len": 7, "cond_latent_frames": 0}
        try:
            ClipDataset(td, expect=geom)  # 4-channel clips vs 48 expected -> all five rejected at construction
            raise AssertionError("geometry scan must raise")
        except ValueError as exc:
            assert "5/5 clips" in str(exc), exc
        s0, s1 = ResumableSampler(5, 0, 2, seed=3), ResumableSampler(5, 1, 2, seed=3)
        a = [s0.next_index() for _ in range(6)]
        b = [s1.next_index() for _ in range(6)]
        assert all(x != y for x, y in zip(a[:2], b[:2], strict=False)) and len(set(a[:2] + b[:2])) == 4
        # Resume replays the same order.
        s0b = ResumableSampler(5, 0, 2, seed=3)
        s0b.load_state_dict(ResumableSampler(5, 0, 2, seed=3).state_dict())
        [s0b.next_index() for _ in range(3)]
        st = s0b.state_dict()
        s0c = ResumableSampler(5, 0, 2, seed=3)
        s0c.load_state_dict(st)
        assert [s0c.next_index() for _ in range(3)] == a[3:6]
        torch.save(
            {
                "latent": torch.randn(1, 4, 3, 4, 6),
                "text_ids": torch.arange(7),
                "cond_latent_frames": 0,
            },
            Path(td) / "bad.pt",
        )
        try:
            ds2 = ClipDataset(td)  # 'bad.pt' sorts first and sets the run shape (T=3)
            ds2[0]
            ds2[1]  # clip0 has T=2 -> mismatch
            raise AssertionError("shape mismatch must raise")
        except ValueError:
            pass
    print("dataset smoke OK")
