# tvid — lecteur et désentrelaceur pour le TP TVID

Dossier de travail du TP « Décompression et affichage de flux vidéo ».

| Fichier | Rôle |
|---|---|
| `../src/mpeg2dec.c` | mpeg2dec patché : option `-l <log>` (flags par image, `frame_period`, `progressive_sequence`) |
| `main.py` | Lecteur : PGM → RGB, sortie PPM ou écran, cadence, weave / bob / adaptive |
| `verif.py` | Vérifications chiffrées (peigne, test O/K, scintillement) |
| `RAPPORT.md` | Brouillon du rapport, question par question |

## Prérequis

`uv` (gère Python 3.14, numpy et pygame-ce dans `.venv/`), `ffmpeg`/`ffplay` pour les comparaisons.

## Compiler mpeg2dec (Mac Apple Silicon)

```sh
cd ..   # racine de mpeg2dec
./configure ac_cv_build=aarch64-apple-darwin ac_cv_host=aarch64-apple-darwin \
            --disable-sdl --without-x CFLAGS="-O2 -fgnu89-inline"
make
```
Le simple `./configure && make` échoue sur M1/M2 (assembleur ARM 32 bits, symboles `inline` dupliqués).

## Décoder

Dans un dossier hors du dépôt (ça pèse de 0,3 à 2 Go par flux) :
```sh
mkdir -p ~/epita/ing3/tvid/work/pend && cd ~/epita/ing3/tvid/work/pend
~/epita/ing3/tvid/mpeg2dec/src/mpeg2dec -o pgm -l flags.log <fichier.m2v>
# flux .ts : ajouter -t <pid>   (cnn : 0x1422, ctv : 0x3e9 / 0x3f3 / 0x3fd)
```

## Lire

```sh
uv run main.py <dossier>                         # bob, cadence du flux
uv run main.py <dossier> --deint weave|bob|adaptive
uv run main.py <dossier> --fps 10                # cadence forcée (prioritaire)
uv run main.py <dossier> --force-interlaced --tff   # ignorer les flags (cnn)
uv run main.py <dossier> --start 760 --max-frames 200
uv run main.py <dossier> --ppm <sortie> --max-frames 20   # écrire des PPM
```
Touches : espace = pause, → = image suivante en pause, q = quitter.
La barre de titre affiche le n° d'image et ses flags.

## Vérifier

```sh
uv run verif.py ~/epita/ing3/tvid/work
```
