"""pwm — Cosmos3-Nano on AWS Trainium2, natively in PyTorch (``device="neuron"``).

Loads the public Cosmos3-Nano diffusers checkpoint (or the released PWM-WROP weights), trains (TP × FSDP2) and
samples (UniPC) on Neuron. The only upstream code carried over is the UniPC solver (``inference/unipc.py``,
with its origin noted in the file); the rest is written here.

Layout: ``model/ data/ parallel/ training/ inference/ configs/``, ``cli.py`` and ``launch.sh``.
``python -m pwm.<pkg>.<module>`` runs a hardware-free ``__main__`` smoke in every library module
(``model.load`` skips without the checkpoint; ``model.consolidate`` has none).
"""
