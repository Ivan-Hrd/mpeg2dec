# Lecteur pour les piles de PGM sorties par mpeg2dec (-o pgm -l flags.log)
# Usage : uv run main.py <dossier> [--deint weave|bob|adaptive] [--fps N] [--ppm sortie]

import argparse
import time
from pathlib import Path

import numpy as np


def read_log(path):
    seq = None
    frames = []

    with open(path) as file:
        for line in file:
            words = line.split()
            data = {}
            for word in words:
                if ("=" in word):
                    key, val = word.split("=")
                    data[key] = val

            if (words[0] == "SEQ" and seq is None):
                seq = data
            elif (words[0] == "FRAME"):
                data["n"] = words[1]
                frames.append(data)

    return seq, frames


def read_pgm(path, height):
    with open(path, "rb") as file:
        data = file.read()

    header, size, max_val, pixels = data.split(b"\n", 3)
    w, h = map(int, size.split())
    img = np.frombuffer(pixels, dtype=np.uint8)
    img = img.reshape(h, w).astype(np.float32)

    # Y en haut, U et V côte à côte en bas.
    y = img[:height]
    u = img[height:, :w // 2]
    v = img[height:, w // 2:]
    return y, u, v


def interp(plane, step, offset, n):
    # Position des lignes à reconstruire entre les lignes du plan d'origine.
    pos = (np.arange(n) - offset) / step
    pos = np.clip(pos, 0, len(plane) - 1)
    i0 = pos.astype(int)
    i1 = np.minimum(i0 + 1, len(plane) - 1)
    a = (pos - i0)[:, None]

    res = plane[i0] * (1 - a) + plane[i1] * a
    return res


def to_rgb(y, u, v, parity=None):
    h, w = y.shape
    if (parity is None):
        u = interp(u, 2, 0.5, h)
        v = interp(v, 2, 0.5, h)
    else:
        # Bob : garder une trame et compléter les lignes manquantes.
        offset = 0.5 + 2 * parity
        u = interp(u[parity::2], 4, offset, h)
        v = interp(v[parity::2], 4, offset, h)
        y = interp(y[parity::2], 2, parity, h)

    # Agrandir aussi la chroma horizontalement.
    u = interp(u.T, 2, 0, w).T
    v = interp(v.T, 2, 0, w).T

    # BT.601
    y = (y - 16) * 1.164
    u = u - 128
    v = v - 128
    r = y + 1.596 * v
    g = y - 0.392 * u - 0.813 * v
    b = y + 2.017 * u

    rgb = np.stack([r, g, b], axis=-1)
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    return rgb


def motion(a, b, block, threshold):
    diff = np.abs(a - b)
    h, w = diff.shape
    nb_y = h // block
    nb_x = w // block

    blocks = diff.reshape(nb_y, block, nb_x, block)
    score = blocks.mean(axis=(1, 3))
    mask = score > threshold

    # Ajouter les blocs voisins pour garder les bords des objets en mouvement.
    padded = np.pad(mask, 1)
    for dy in range(3):
        for dx in range(3):
            mask = mask | padded[dy:dy + nb_y, dx:dx + nb_x]

    res = mask.repeat(block, 0).repeat(block, 1)
    res = res.repeat(2, 0)
    return res


def images(args, files, seq, flags):
    if (args.fps):
        period = 1 / args.fps
    elif (int(seq["frame_period"])):
        period = int(seq["frame_period"]) / 27e6
    else:
        period = 1 / 25

    last_y = []
    last_rgb = []
    for path, f in zip(files, flags):
        y, u, v = read_pgm(path, int(seq["height"]))
        progressive = f["progressive_frame"] == "1"
        tff = f["top_field_first"] == "1"
        rff = f["repeat_first_field"] == "1"
        if (args.force_progressive):
            progressive = True
        if (args.force_interlaced):
            progressive = False
        if (args.tff):
            tff = True
        if (args.bff):
            tff = False

        title = f"#{f['n']} {f['type']} "
        if (progressive):
            title += "P"
        elif (tff):
            title += "I TFF"
        else:
            title += "I BFF"

        if (progressive or args.deint == "weave"):
            last_y = []
            last_rgb = []
            duration = period
            if (rff):
                duration *= 1.5
            rgb = to_rgb(y, u, v)
            yield rgb, duration, title
            continue

        order = [0, 1] if tff else [1, 0]
        if (rff):
            order.append(order[0])
        for p in order:
            bob = to_rgb(y, u, v, p)
            res = bob
            if (args.deint == "adaptive" and len(last_y) >= 3):
                # Comparer t avec t-2, et t-1 avec t-3.
                field = y[p::2]
                old_field = last_y[-2][p::2]
                mask = motion(field, old_field, args.block, args.threshold)

                prev_field = last_y[-1][1 - p::2]
                old_field = last_y[-3][1 - p::2]
                prev_mask = motion(prev_field, old_field, args.block, args.threshold)
                mask = mask | prev_mask

                # Weave seulement sur les lignes manquantes des zones immobiles.
                weave = ~mask
                weave[p::2] = False
                res = bob.copy()
                res[weave] = last_rgb[-1][weave]

            last_y.append(y)
            last_rgb.append(bob)
            if (len(last_y) > 3):
                last_y.pop(0)
                last_rgb.pop(0)

            yield res, period / 2, title + " field " + "TB"[p]


def show(frames):
    import pygame

    pygame.init()
    screen = None
    paused = False
    nb_frame = 0
    start = time.perf_counter()
    next_time = start
    for rgb, duration, title in frames:
        h, w, _ = rgb.shape
        if (screen is None):
            screen = pygame.display.set_mode((w, h))

        while True:
            for event in pygame.event.get():
                if (event.type == pygame.QUIT):
                    return
                if (event.type == pygame.KEYDOWN):
                    if (event.key == pygame.K_q):
                        return
                    if (event.key == pygame.K_SPACE):
                        paused = not paused
            if (not paused):
                break
            time.sleep(0.02)
            next_time = time.perf_counter()

        surface = pygame.surfarray.make_surface(rgb.swapaxes(0, 1))
        screen.blit(surface, (0, 0))
        time.sleep(max(0, next_time - time.perf_counter()))
        pygame.display.flip()
        pygame.display.set_caption(title)
        next_time += duration
        nb_frame += 1

    elapsed = time.perf_counter() - start
    print(f"{nb_frame} images en {elapsed:.2f} s ({nb_frame / elapsed:.2f} img/s)")


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
    args = parser.parse_args()

    folder = Path(args.dir)
    seq, flags = read_log(folder / "flags.log")
    files = sorted(folder.glob("*.pgm"), key=lambda f: int(f.stem))
    print(f"{len(files)} images {seq['width']}x{seq['height']}, frame_period={seq['frame_period']}, "
          f"progressive_sequence={seq['progressive_sequence']}")

    frames = images(args, files, seq, flags)

    if (args.ppm):
        out = Path(args.ppm)
        out.mkdir(exist_ok=True)
        for n, (rgb, _, _) in enumerate(frames):
            h, w, _ = rgb.shape
            path = out / f"{n:06d}.ppm"
            header = f"P6\n{w} {h}\n255\n"
            with open(path, "wb") as file:
                file.write(header.encode())
                file.write(rgb.tobytes())
    else:
        show(frames)


if (__name__ == "__main__"):
    main()
