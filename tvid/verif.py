# Mesures pour vérifier le lecteur sans tout regarder à l'oeil
# Usage : uv run verif.py <work>   (dossiers pend, cnn, ctv3 décodés avec mpeg2dec -l flags.log)

import sys
from argparse import Namespace
from pathlib import Path

import numpy as np

import main

work = Path(sys.argv[1])


def frames(name, start, count, **options):
    args = dict(fps=None, deint="bob", threshold=10, block=16, force_progressive=False,
                force_interlaced=False, tff=False, bff=False)
    args.update(options)
    seq, flags = main.read_log(work / name / "flags.log")
    files = sorted((work / name).glob("*.pgm"), key=lambda f: int(f.stem))
    gen = main.images(Namespace(**args), files[start:], seq, flags[start:])
    return [rgb for _, (rgb, _, _) in zip(range(count), gen)]


def luma(rgb):
    return rgb @ np.array([0.299, 0.587, 0.114])


def comb(rgb):
    # % de pixels dont la ligne s'écarte de ses deux voisines dans le même sens
    y = luma(rgb)
    c = (y[1:-1] - y[:-2]) * (y[1:-1] - y[2:])
    return 100 * (c > 400).mean()


print("pendulum, peigne sur le pendule (images 100-160)")
for mode in ["weave", "bob", "adaptive"]:
    imgs = frames("pend", 100, 60, deint=mode)
    print(f"  {mode:9} {np.mean([comb(i[:380]) for i in imgs]):.2f} %")

print("pendulum entier, test O/K")
for mode in ["bob", "adaptive"]:
    imgs = frames("pend", 0, 2000, deint=mode)
    both = 0
    combed = 0
    for img in imgs:
        letters = luma(img)[420:475, 290:430] > 100
        both += letters[:, :55].mean() > 0.03 and letters[:, 65:].mean() > 0.03
        combed += comb(img[:380]) > 0.2
    print(f"  {mode:9} O et K ensemble : {both}/{len(imgs)}, images avec peigne : {combed}")

print("cnn, peigne (flags respectés / entrelacé forcé)")
for start, count, name in [(0, 470, "0-470, marquées P"), (480, 360, "480-840, marquées I")]:
    normal = np.mean([comb(i) for i in frames("cnn", start, count)])
    forced = np.mean([comb(i) for i in frames("cnn", start, count, force_interlaced=True, tff=True)])
    print(f"  {name:20} {normal:.2f} % / {forced:.2f} %")

print("ctv 0x3fd, scène du gâteau, peigne (flags respectés / entrelacé forcé)")
for start, count, name in [(30, 40, "30-69, I"), (90, 90, "90-179, P"), (200, 60, "200-259, I")]:
    normal = np.mean([comb(i) for i in frames("ctv3", start, count)])
    forced = np.mean([comb(i) for i in frames("ctv3", start, count, force_interlaced=True, bff=True)])
    print(f"  {name:20} {normal:.2f} % / {forced:.2f} %")

print("ctv 0x3fd, scintillement entre deux images (images 2000-2060)")
for mode in ["bob", "adaptive"]:
    imgs = [luma(i) for i in frames("ctv3", 2000, 120, deint=mode, force_interlaced=True, bff=True)]
    whole = np.mean([np.abs(imgs[i] - imgs[i - 1]).mean() for i in range(1, len(imgs))])
    poster = np.mean([np.abs(imgs[i][40:300, :200] - imgs[i - 1][40:300, :200]).mean() for i in range(1, len(imgs))])
    print(f"  {mode:9} image {whole:.2f}, affiche {poster:.2f}")
