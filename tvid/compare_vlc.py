"""Capture du rendu de libVLC sans fenêtre, pour les comparaisons du TP.

Usage : uv run compare_vlc.py <video> <bob|x|weave> <largeur> <dossier>
Les captures PPM gardent une taille fixée par la commande (hauteur 480).
"""

import argparse
import ctypes as C
import time
from pathlib import Path

import numpy as np

lib = C.CDLL('libvlc.so.5')
def api(name, result, arguments):
    f = getattr(lib, 'libvlc_' + name)
    f.restype = result
    f.argtypes = arguments
    return f

ptr = C.c_void_p
new = api('new', ptr, [C.c_int, C.POINTER(C.c_char_p)])
media_new = api('media_new_path', ptr, [ptr, C.c_char_p])
player_new = api('media_player_new_from_media', ptr, [ptr])
set_format = api('video_set_format', None, [ptr, C.c_char_p, C.c_uint, C.c_uint, C.c_uint])
set_deint = api('video_set_deinterlace', None, [ptr, C.c_char_p])
play = api('media_player_play', C.c_int, [ptr])
state = api('media_player_get_state', C.c_int, [ptr])
stop = api('media_player_stop', None, [ptr])
release_player = api('media_player_release', None, [ptr])
release_media = api('media_release', None, [ptr])
release = api('release', None, [ptr])
LOCK = C.CFUNCTYPE(ptr, ptr, C.POINTER(ptr))
UNLOCK = C.CFUNCTYPE(None, ptr, ptr, C.POINTER(ptr))
DISPLAY = C.CFUNCTYPE(None, ptr, ptr)
callbacks = api('video_set_callbacks', None, [ptr, LOCK, UNLOCK, DISPLAY, ptr])

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('file')
parser.add_argument('mode', choices=['bob', 'x', 'weave'])
parser.add_argument('width', type=int)
parser.add_argument('output')
args = parser.parse_args()
file, mode, width, output = args.file, args.mode, args.width, args.output
if width <= 0:
    parser.error('La largeur doit être strictement positive.')
w, h = int(width), 480
buffer = (C.c_ubyte * (w*h*4))()
scores = []
samples = {}

def comb(rgb):
    y = rgb @ np.array([.299, .587, .114])
    return 100*np.mean((y[1:-1]-y[:-2])*(y[1:-1]-y[2:]) > 400)

@LOCK
def lock(opaque, planes):
    planes[0] = C.cast(buffer, ptr)
    return None
@UNLOCK
def unlock(opaque, picture, planes):
    pass
@DISPLAY
def display(opaque, picture):
    bgr = np.ctypeslib.as_array(buffer).reshape(h, w, 4)
    rgb = bgr[:, :, :3][:, :, ::-1]
    i = len(scores)
    if 10 <= i < 14 or 180 <= i < 184:
        samples[i] = rgb.copy()
    scores.append(comb(rgb))

options = [b'--no-audio', b'--avcodec-hw=none', b'--no-video-title-show',
           b'--deinterlace=1', ('--deinterlace-mode='+mode).encode(),
           b'--no-drop-late-frames', b'--no-skip-frames', b'--quiet']
instance = new(len(options), (C.c_char_p * len(options))(*options))
if not instance:
    raise RuntimeError('libvlc_new failed')
media = media_new(instance, str(Path(file).resolve()).encode())
player = player_new(media)
callbacks(player, lock, unlock, display, None)
set_format(player, b'RV32', w, h, w*4)
set_deint(player, mode.encode())
if play(player):
    raise RuntimeError('play failed')
deadline = time.monotonic()+30
while time.monotonic() < deadline and state(player) not in (6,7):
    time.sleep(.05)
finished = state(player)
stop(player)
release_player(player)
release_media(media)
release(instance)
out = Path(output)
out.mkdir(exist_ok=True, parents=True)
for i, rgb in samples.items():
    (out/f'{i}.ppm').write_bytes(f'P6\n{w} {h}\n255\n'.encode() + rgb.tobytes())
if finished != 6 or not scores:
    raise RuntimeError(f'Lecture VLC incomplète : état {finished}, {len(scores)} captures.')
print(mode, len(scores), 'images, indicateur de peigne moyen', np.mean(scores))

