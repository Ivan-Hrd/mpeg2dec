# tvid — lecteur et désentrelaceur pour le TP TVID

Dossier de travail du TP « Décompression et affichage de flux vidéo ».

| Fichier | Rôle |
|---|---|
| `../src/mpeg2dec.c` | mpeg2dec patché : option `-l <log>` (flags par image, `frame_period`, `progressive_sequence`) |
| `main.py` | Lecteur : PGM → RGB, sortie PPM ou écran, cadence, weave / bob / adaptive |
| `verif.py` | Vérifications chiffrées (peigne, test O/K, scintillement) |
| `RAPPORT.md` | Rapport, question par question, avec les limites des mesures |
| `test_main.py` | Tests des cas limites du lecteur |
| `compare_vlc.py` | Captures de référence via libVLC, sans fenêtre (Linux) |

## Prérequis

`uv` (gère Python 3.14, numpy et pygame-ce dans `.venv/`), `ffmpeg`/`ffplay` et VLC pour
les comparaisons. Depuis ce dossier, `uv sync` installe l'environnement Python.

## Compiler mpeg2dec (commandes vérifiées sous Linux x86-64)

```sh
cd ..   # racine de mpeg2dec
./configure --disable-sdl --without-x CFLAGS="-O2 -fgnu89-inline"
make -j2
./src/mpeg2dec -h
```
L'aide doit contenir `-l`. Le statut de sortie de `-h` vaut 1 dans cet ancien programme.
`-fgnu89-inline` conserve la sémantique des fonctions inline attendue par ce code ancien.
Les options SDL/X désactivées concernent les sorties de mpeg2dec ; le lecteur utilise pygame.

## Décoder

Depuis la racine du dépôt, avec les chemins de cette machine :
```sh
REPO=$(pwd)
VIDEOS=/home/steeve/Bureau/git/tvid/VIDEO/TP/videos
mkdir -p output/validation/pend output/validation/cnn output/validation/ctv3 output/validation/ctv1
(cd output/validation/pend && "$REPO/src/mpeg2dec" -o pgm -l flags.log "$VIDEOS/elementary/pendulum.m2v")
(cd output/validation/cnn && "$REPO/src/mpeg2dec" -o pgm -l flags.log -t 0x1422 "$VIDEOS/ts/cnn.ts")
(cd output/validation/ctv3 && "$REPO/src/mpeg2dec" -o pgm -l flags.log -t 0x3fd "$VIDEOS/ts/ctv.ts")
(cd output/validation/ctv1 && "$REPO/src/mpeg2dec" -o pgm -l flags.log -t 0x3e9 "$VIDEOS/ts/ctv.ts")
```

Ces quatre piles occupent environ 4,6 Go. Les logs et les images sont dans le même dossier.
Les anciens PGM de `output/pendulum` restent disponibles ; le lecteur utilise les nouvelles piles
accompagnées de `flags.log`. Il associe les flags au numéro du fichier et signale les flags manquants.

## Lire

```sh
uv run main.py <dossier>                         # bob, cadence du flux
uv run main.py <dossier> --deint adaptive         # choix : weave, bob ou adaptive
uv run main.py <dossier> --fps 10                # cadence forcée (prioritaire)
uv run main.py <dossier> --force-interlaced --tff   # ignorer les flags (cnn)
uv run main.py <dossier> --start 760 --max-frames 200
uv run main.py <dossier> --ppm <sortie> --max-frames 20   # écrire des PPM
```
Touches : espace = pause, → = image suivante en pause, q = quitter.
La barre de titre affiche le n° d'image et ses flags.

`--start` compte les images sources ; `--max-frames` limite les images de sortie (deux par source
entrelacée en bob, hors répétitions). `--fps` fixe la cadence de base des sources ; bob utilise
des demi-périodes. Sans `--fps`, la priorité est `frame_period`, puis 25 ips si cette valeur
est absente ou nulle. Le fichier `flags.log` reste nécessaire pour connaître la géométrie et les flags.
Le lecteur prend en charge la disposition PGM Y/U/V 4:2:0 sur 8 bits utilisée dans ce TP.
Les deux rendus bob sont calculés sur deux threads ; les décisions de l'adaptatif restent
séquentielles pour préserver l'ordre temporel.

`--block N` règle les blocs dans les coordonnées du field, y compris les blocs incomplets au bord.
`--threshold N` règle le seuil de mouvement. Les options progressif/entrelacé forcé sont exclusives,
comme les options TFF/BFF.

## Vérifier

```sh
uv run python -m unittest -v test_main.py
uv run verif.py ../output/validation
```

Les comparaisons sélectionnent les mêmes images sources avant bob/weave. L'indicateur de peigne
est une heuristique sensible aux textures et au texte ; il complète l'observation visuelle.

Pour reproduire une capture de référence de VLC, sur un court extrait MPEG-2 en TS :

```sh
uv run compare_vlc.py ../output/validation/clip-pend.ts bob 720 ../output/validation/vlc-repro-pend
uv run compare_vlc.py ../output/validation/clip-ctv3-static.ts x 704 ../output/validation/vlc-repro-x
```

Ces extraits ont été créés pendant la validation. Le script utilise `libvlc.so.5`, force le filtre
choisi, conserve des captures PPM et affiche un indicateur moyen. La hauteur est fixée à 480,
et la lecture est limitée à 30 secondes. Les numéros de captures ne sont pas ceux des PGM sources.
Pour la lecture interactive de CTV avec VLC :

```sh
vlc --program=102 --deinterlace=1 --deinterlace-mode=x /home/steeve/Bureau/git/tvid/VIDEO/TP/videos/ts/ctv.ts
```
