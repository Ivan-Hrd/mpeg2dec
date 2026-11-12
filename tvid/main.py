# Lecteur pour les piles de PGM sorties par mpeg2dec (-o pgm -l flags.log)
# Usage : uv run main.py <dossier> [--deint weave|bob|adaptive] [--fps N] [--ppm sortie]

import argparse
import time
from pathlib import Path

import numpy as np


def read_log(path):
    # SEQ width=.. height=.. frame_period=.. / FRAME n type=.. progressive_frame=.. ...
    seq = None
    frames = []
    for line in open(path):
        words = line.split()
        values = dict(w.split("=") for w in words if "=" in w)
        if words[0] == "SEQ" and seq is None:
            seq = values
        elif words[0] == "FRAME":
            values["n"] = words[1]
            frames.append(values)
    return seq, frames


def read_pgm(path, height):
    # mpeg2dec écrit Y en haut, puis U et V côte à côte en dessous
    data = open(path, "rb").read()
    _, size, _, pixels = data.split(b"\n", 3)
    w, h = map(int, size.split())
    img = np.frombuffer(pixels, np.uint8).reshape(h, w).astype(np.float32)
    return img[:height], img[height:, :w // 2], img[height:, w // 2:]


def interp(plane, step, offset, n):
    # la ligne i de plane est à la hauteur step*i + offset dans l'image finale,
    # on interpole linéairement pour obtenir les lignes 0..n-1
    pos = np.clip((np.arange(n) - offset) / step, 0, len(plane) - 1)
    i0 = pos.astype(int)
    i1 = np.minimum(i0 + 1, len(plane) - 1)
    a = (pos - i0)[:, None]
    return plane[i0] * (1 - a) + plane[i1] * a


def to_rgb(y, u, v, parity=None):
    h, w = y.shape
    if parity is None:
        # image progressive : chroma 4:2:0 placée entre deux lignes de luma
        u = interp(u, 2, 0.5, h)
        v = interp(v, 2, 0.5, h)
    else:
        # bob : on ne garde qu'un field (0 = top, 1 = bottom) et on le remet
        # à la bonne hauteur. Chaque field a sa propre chroma, décalée selon
        # la parité (ligne chroma k du field -> hauteur 4k + 0.5 + 2*parité)
        u = interp(u[parity::2], 4, 0.5 + 2 * parity, h)
        v = interp(v[parity::2], 4, 0.5 + 2 * parity, h)
        y = interp(y[parity::2], 2, parity, h)
    # horizontalement la chroma est alignée sur les colonnes paires
    u = interp(u.T, 2, 0, w).T
    v = interp(v.T, 2, 0, w).T

    # BT.601
    y = (y - 16) * 1.164
    u = u - 128
    v = v - 128
    rgb = np.stack([y + 1.596 * v, y - 0.392 * u - 0.813 * v, y + 2.017 * u], axis=-1)
    return np.clip(rgb, 0, 255).astype(np.uint8)


def motion(a, b, block, threshold):
    # a et b : deux fields de même parité. Renvoie le masque des zones qui
    # bougent, à la taille de l'image entière
    d = np.abs(a - b)
    h, w = d.shape
    m = d.reshape(h // block, block, w // block, block).mean(axis=(1, 3)) > threshold
    # on élargit d'un bloc autour des zones qui bougent (sinon les bords
    # fins comme le bras du pendule passent sous le seuil)
    p = np.pad(m, 1)
    for dy in range(3):
        for dx in range(3):
            m = m | p[dy:dy + h // block, dx:dx + w // block]
    return m.repeat(block, 0).repeat(block, 1).repeat(2, 0)


def images(args, files, seq, flags):
    if args.fps:
        period = 1 / args.fps
    elif int(seq["frame_period"]):
        period = int(seq["frame_period"]) / 27e6
    else:
        period = 1 / 25

    history = []  # derniers fields affichés : (parité, luma de l'image, rendu bob)
    for path, f in zip(files, flags):
        y, u, v = read_pgm(path, int(seq["height"]))
        progressive = f["progressive_frame"] == "1"
        tff = f["top_field_first"] == "1"
        rff = f["repeat_first_field"] == "1"
        if args.force_progressive:
            progressive = True
        if args.force_interlaced:
            progressive = False
        if args.tff:
            tff = True
        if args.bff:
            tff = False

        title = f"#{f['n']} {f['type']} " + ("P" if progressive else "I TFF" if tff else "I BFF")

        if progressive or args.deint == "weave":
            history = []
            yield to_rgb(y, u, v), period * (1.5 if rff else 1), title
            continue

        order = [0, 1] if tff else [1, 0]
        if rff:
            order.append(order[0])
        for p in order:
            bob = to_rgb(y, u, v, p)
            out = bob
            if args.deint == "adaptive" and len(history) >= 3:
                # t-1 est le field qu'on va tisser, t-2 et t-3 servent de
                # référence de même parité pour t et t-1
                prev = history[-1]
                moving = motion(y[p::2], history[-2][1][p::2], args.block, args.threshold)
                moving |= motion(prev[1][1 - p::2], history[-3][1][1 - p::2], args.block, args.threshold)
                weave = ~moving
                weave[p::2] = False  # les lignes du field courant restent toujours
                out = np.where(weave[:, :, None], prev[2], bob)
            history = (history + [(p, y, bob)])[-3:]
            yield out, period / 2, title + " field " + "TB"[p]


def show(frames, scale):
    import pygame

    pygame.init()
    screen = None
    paused = False
    count = 0
    start = next_time = time.perf_counter()
    for rgb, duration, title in frames:
        h, w, _ = rgb.shape
        if screen is None:
            screen = pygame.display.set_mode((w * scale, h * scale))

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_q):
                    return
                if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                    paused = not paused
            if not paused:
                break
            time.sleep(0.02)
            next_time = time.perf_counter()

        surface = pygame.surfarray.make_surface(rgb.swapaxes(0, 1))
        screen.blit(pygame.transform.scale(surface, (w * scale, h * scale)), (0, 0))
        time.sleep(max(0, next_time - time.perf_counter()))
        pygame.display.flip()
        pygame.display.set_caption(title)
        next_time += duration
        count += 1

    elapsed = time.perf_counter() - start
    print(f"{count} images en {elapsed:.2f} s ({count / elapsed:.2f} img/s)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dir")
    parser.add_argument("--ppm", help="dossier de sortie (sinon affichage)")
    parser.add_argument("--fps", type=float)
    parser.add_argument("--deint", choices=["weave", "bob", "adaptive"], default="bob")
    parser.add_argument("--threshold", type=float, default=10)
    parser.add_argument("--block", type=int, default=16)
    parser.add_argument("--force-progressive", action="store_true")
    parser.add_argument("--force-interlaced", action="store_true")
    parser.add_argument("--tff", action="store_true")
    parser.add_argument("--bff", action="store_true")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--scale", type=int, default=1)
    args = parser.parse_args()

    folder = Path(args.dir)
    seq, flags = read_log(folder / "flags.log")
    files = sorted(folder.glob("*.pgm"), key=lambda f: int(f.stem))
    files = files[args.start:]
    flags = flags[args.start:]
    print(f"{len(files)} images {seq['width']}x{seq['height']}, frame_period={seq['frame_period']}, "
          f"progressive_sequence={seq['progressive_sequence']}")

    frames = images(args, files, seq, flags)
    if args.max_frames:
        frames = (f for _, f in zip(range(args.max_frames), frames))

    if args.ppm:
        out = Path(args.ppm)
        out.mkdir(exist_ok=True)
        for n, (rgb, _, _) in enumerate(frames):
            h, w, _ = rgb.shape
            (out / f"{n:06d}.ppm").write_bytes(f"P6\n{w} {h}\n255\n".encode() + rgb.tobytes())
    else:
        show(frames, args.scale)


if __name__ == "__main__":
    main()
