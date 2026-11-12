# Lecteur pour les piles de PGM sorties par mpeg2dec (-o pgm -l flags.log)
# Usage : uv run main.py <dossier> [--deint weave|bob|adaptive] [--fps N] [--ppm sortie]

import argparse
import math
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np


def read_log(path):
    # SEQ width=.. height=.. frame_period=.. / FRAME n type=.. progressive_frame=.. ...
    seq = None
    frames = []
    current_seq = {}
    with open(path) as stream:
        for line in stream:
            words = line.split()
            if not words or words[0].startswith("#"):
                continue
            values = dict(w.split("=", 1) for w in words if "=" in w)
            if words[0] == "SEQ":
                current_seq = values
                if seq is None:
                    seq = values
            elif words[0] == "FRAME":
                values["n"] = words[1]
                values["sequence"] = current_seq.copy()
                frames.append(values)
    if seq is None:
        raise ValueError("Le log ne contient aucune ligne SEQ.")
    return seq, frames


def load_inputs(folder):
    seq, flags = read_log(folder / "flags.log")
    files = sorted(folder.glob("*.pgm"), key=lambda f: int(f.stem))
    if not files:
        raise ValueError(f"Aucun fichier PGM dans {folder}.")
    by_number = {int(f["n"]): f for f in flags}
    if len(by_number) != len(flags):
        raise ValueError("Numéros FRAME dupliqués dans flags.log.")
    missing = [p.stem for p in files if int(p.stem) not in by_number]
    if missing:
        raise ValueError(f"Flags absents pour les images : {', '.join(missing[:10])}")
    return files, seq, [by_number[int(p.stem)] for p in files]


def read_pgm(path, height):
    # mpeg2dec écrit Y en haut, puis U et V côte à côte en dessous
    data = Path(path).read_bytes()
    magic, size, depth, pixels = data.split(b"\n", 3)
    w, h = map(int, size.split())
    if magic != b"P5" or depth.strip() != b"255":
        raise ValueError(f"{path} : un PGM P5 sur 8 bits est attendu.")
    if w % 2 or height % 4 or h != height * 3 // 2:
        raise ValueError(f"{path} : disposition Y/U/V 4:2:0 attendue, dimensions incompatibles.")
    img = np.frombuffer(pixels, np.uint8).reshape(h, w).astype(np.float32)
    return img[:height], img[height:, :w // 2], img[height:, w // 2:]


def interp(plane, step, offset, n):
    # la ligne i de plane est à la hauteur step*i + offset dans l'image finale,
    # on interpole linéairement pour obtenir les lignes 0..n-1
    pos = np.clip((np.arange(n, dtype=np.float32) - offset) / step, 0, len(plane) - 1)
    i0 = pos.astype(int)
    i1 = np.minimum(i0 + 1, len(plane) - 1)
    a = (pos - i0.astype(np.float32))[:, None]
    return plane[i0] * (1 - a) + plane[i1] * a


def horizontal_chroma(plane):
    # Facteur deux, échantillons MPEG-2 sur les colonnes paires.
    # Les tranches évitent les copies de colonnes transposées à chaque sortie.
    h, w = plane.shape
    out = np.empty((h, 2 * w), dtype=np.float32)
    out[:, ::2] = plane
    out[:, 1:-1:2] = (plane[:, :-1] + plane[:, 1:]) * 0.5
    out[:, -1] = plane[:, -1]
    return out


def to_rgb(y, u, v, parity=None, interlaced=False):
    h, w = y.shape
    if parity is None and interlaced:
        top = to_rgb(y, u, v, 0)
        bottom = to_rgb(y, u, v, 1)
        top[1::2] = bottom[1::2]
        return top
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
        field = y[parity::2]
        y = np.empty_like(y)
        y[parity::2] = field
        middle = (field[:-1] + field[1:]) * 0.5
        if parity == 0:
            y[1:-1:2] = middle
            y[-1] = field[-1]
        else:
            y[2::2] = middle
            y[0] = field[0]
    # horizontalement la chroma est alignée sur les colonnes paires
    u = horizontal_chroma(u)
    v = horizontal_chroma(v)

    # BT.601
    y = y - 16
    y *= 1.164
    u -= 128
    v -= 128
    rgb = np.stack([y + 1.596 * v, y - 0.392 * u - 0.813 * v, y + 2.017 * u], axis=-1)
    np.clip(rgb, 0, 255, out=rgb)
    return rgb.astype(np.uint8)


def motion(a, b, block, threshold):
    # a et b : deux fields de même parité. Renvoie le masque des zones qui
    # bougent, à la taille de l'image entière
    d = np.abs(a.astype(np.float32) - b.astype(np.float32))
    h, w = d.shape
    rows = np.arange(0, h, block)
    cols = np.arange(0, w, block)
    totals = np.add.reduceat(np.add.reduceat(d, rows, axis=0), cols, axis=1)
    sizes = np.minimum(block, h - rows)[:, None] * np.minimum(block, w - cols)[None, :]
    m = totals / sizes > threshold
    # on élargit d'un bloc autour des zones qui bougent (sinon les bords
    # fins comme le bras du pendule passent sous le seuil)
    p = np.pad(m, 1)
    for dy in range(3):
        for dx in range(3):
            m = m | p[dy:dy + len(rows), dx:dx + len(cols)]
    return m.repeat(block, 0)[:h].repeat(block, 1)[:, :w].repeat(2, 0)


def frame_period(fps, seq):
    if fps is not None:
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError("La cadence doit être strictement positive et finie.")
        return 1 / fps
    ticks = int(seq.get("frame_period", 0))
    return ticks / 27e6 if ticks > 0 else 1 / 25


def images(args, files, seq, flags):
    # Les deux reconstructions bob sont indépendantes ; NumPy peut les calculer
    # en parallèle. Les décisions temporelles de l'adaptatif restent séquentielles.
    with ThreadPoolExecutor(max_workers=2) as executor:
        yield from _images(args, files, seq, flags, executor)


def _images(args, files, seq, flags, executor):
    history = []  # derniers fields affichés : (parité, luma de l'image, rendu bob)
    previous_sequence = None
    for path, f in zip(files, flags):
        current_seq = f.get("sequence", seq)
        if current_seq != previous_sequence:
            history = []
            previous_sequence = current_seq
        period = frame_period(args.fps, current_seq)
        y, u, v = read_pgm(path, int(current_seq["height"]))
        progressive = (current_seq.get("progressive_sequence", "0") == "1"
                       or f["progressive_frame"] == "1")
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
        nb_fields = int(f.get("nb_fields", 3 if rff else 2))
        if nb_fields not in (2, 3, 4, 6):
            raise ValueError(f"Image {f['n']} : nombre de fields non pris en charge : {nb_fields}")

        title = f"#{f['n']} {f['type']} " + ("P" if progressive else "I TFF" if tff else "I BFF")

        if progressive or args.deint == "weave":
            history = []
            yield to_rgb(y, u, v, interlaced=not progressive), period * nb_fields / 2, title
            continue

        order = [0, 1] if tff else [1, 0]
        order = (order * 3)[:nb_fields]
        rendered = {p: executor.submit(to_rgb, y, u, v, p) for p in (0, 1)}
        for p in order:
            # Un changement TFF/BFF ou un field répété peut casser l'alternance.
            if history and history[-1][0] == p:
                history = []
            bob = rendered[p].result()
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
    stepped = False
    count = 0
    start = next_time = time.perf_counter()
    for rgb, duration, title in frames:
        if stepped:
            paused = True
            stepped = False
        h, w, _ = rgb.shape
        if screen is None:
            screen = pygame.display.set_mode((w * scale, h * scale))

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_q):
                    pygame.quit()
                    return
                if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                    paused = not paused
                    next_time = time.perf_counter()
                if event.type == pygame.KEYDOWN and event.key == pygame.K_RIGHT and paused:
                    stepped = True
            if not paused or stepped:
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

    time.sleep(max(0, next_time - time.perf_counter()))
    elapsed = time.perf_counter() - start
    pygame.quit()
    print(f"{count} images en {elapsed:.2f} s ({count / elapsed:.2f} img/s)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dir")
    parser.add_argument("--ppm", help="dossier de sortie (sinon affichage)")
    parser.add_argument("--fps", type=float)
    parser.add_argument("--deint", choices=["weave", "bob", "adaptive"], default="bob")
    parser.add_argument("--threshold", type=float, default=10)
    parser.add_argument("--block", type=int, default=16)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--force-progressive", action="store_true")
    mode.add_argument("--force-interlaced", action="store_true")
    order = parser.add_mutually_exclusive_group()
    order.add_argument("--tff", action="store_true")
    order.add_argument("--bff", action="store_true")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--scale", type=int, default=1)
    args = parser.parse_args()
    if args.fps is not None and (not math.isfinite(args.fps) or args.fps <= 0):
        parser.error("--fps doit être strictement positif et fini")
    if args.block <= 0 or args.scale <= 0:
        parser.error("--block et --scale doivent être strictement positifs")
    if not math.isfinite(args.threshold) or args.threshold < 0:
        parser.error("--threshold doit être positif ou nul et fini")
    if args.start < 0 or args.max_frames < 0:
        parser.error("--start et --max-frames doivent être positifs ou nuls")

    folder = Path(args.dir)
    try:
        files, seq, flags = load_inputs(folder)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    files = files[args.start:]
    flags = flags[args.start:]
    print(f"{len(files)} images {seq['width']}x{seq['height']}, frame_period={seq.get('frame_period', 0)}, "
          f"progressive_sequence={seq.get('progressive_sequence', 'inconnu')}")

    frames = images(args, files, seq, flags)
    if args.max_frames:
        frames = (f for _, f in zip(range(args.max_frames), frames))

    if args.ppm:
        out = Path(args.ppm)
        out.mkdir(parents=True, exist_ok=True)
        for n, (rgb, _, _) in enumerate(frames):
            h, w, _ = rgb.shape
            (out / f"{n:06d}.ppm").write_bytes(f"P6\n{w} {h}\n255\n".encode() + rgb.tobytes())
    else:
        show(frames, args.scale)


if __name__ == "__main__":
    main()
