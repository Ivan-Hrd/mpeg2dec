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
    files, seq, flags = main.load_inputs(work / name)
    # count porte sur les images SOURCES, quel que soit le nombre de sorties.
    gen = main.images(Namespace(**args), files[start:start + count], seq, flags[start:start + count])
    return (rgb for rgb, _, _ in gen)


def luma(rgb):
    return rgb @ np.array([0.299, 0.587, 0.114])


def comb(rgb):
    # % de pixels dont la ligne s'écarte de ses deux voisines dans le même sens
    y = luma(rgb)
    c = (y[1:-1] - y[:-2]) * (y[1:-1] - y[2:])
    return 100 * (c > 400).mean()


print("pendulum, peigne sur le pendule (sources 100-159 incluses)")
for mode in ["weave", "bob", "adaptive"]:
    imgs = frames("pend", 100, 60, deint=mode)
    print(f"  {mode:9} {np.mean([comb(i[:380]) for i in imgs]):.2f} %")

print("pendulum entier, test O/K")
for mode in ["bob", "adaptive"]:
    imgs = frames("pend", 0, 2000, deint=mode)
    both = total = 0
    combed = 0
    for img in imgs:
        total += 1
        letters = luma(img)[420:475, 290:430] > 100
        both += letters[:, :55].mean() > 0.03 and letters[:, 65:].mean() > 0.03
        combed += comb(img[:380]) > 0.2
    print(f"  {mode:9} O et K ensemble : {both}/{total}, images avec peigne : {combed}")

print("cnn, peigne (flags respectés / entrelacé forcé)")
for start, count, name in [(0, 470, "sources 0-469"), (480, 360, "sources 480-839")]:
    normal = np.mean([comb(i) for i in frames("cnn", start, count)])
    forced = np.mean([comb(i) for i in frames("cnn", start, count, force_interlaced=True, tff=True)])
    print(f"  {name:20} {normal:.2f} % / {forced:.2f} %")

print("ctv 0x3fd, scène du gâteau, peigne (flags respectés / entrelacé forcé)")
for start, count, name in [(30, 40, "30-69, I"), (90, 90, "90-179, P"), (200, 60, "200-259, I")]:
    normal = np.mean([comb(i) for i in frames("ctv3", start, count)])
    forced = np.mean([comb(i) for i in frames("ctv3", start, count, force_interlaced=True, bff=True)])
    print(f"  {name:20} {normal:.2f} % / {forced:.2f} %")

print("ctv 0x3fd, scintillement entre sorties (sources 2000-2059 incluses)")
for mode in ["bob", "adaptive"]:
    previous = None
    whole_changes, poster_changes = [], []
    for rgb in frames("ctv3", 2000, 60, deint=mode, force_interlaced=True, bff=True):
        img = luma(rgb)
        if previous is not None:
            whole_changes.append(np.abs(img - previous).mean())
            poster_changes.append(np.abs(img[40:300, :200] - previous[40:300, :200]).mean())
        previous = img
    whole = np.mean(whole_changes)
    poster = np.mean(poster_changes)
    print(f"  {mode:9} image {whole:.2f}, affiche {poster:.2f}")
