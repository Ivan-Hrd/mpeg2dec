# TP TVID : décompression et affichage de flux vidéo

Outils utilisés :
- `mpeg2dec` modifié
- `main.py`, notre lecteur en Python (numpy + pygame) : conversion en RGB, sortie PPM ou écran, cadence, désentrelacement bob et adaptatif
- `verif.py`, quelques mesures pour vérifier les résultats

## A. Jouer un flux MPEG-2 élémentaire de test :

A.1 : On a choisit pendulum.m2v.

A.2 :
```sh
mpeg2dec -o pgm pendulum.m2v
```
On obtient 533 images, de "0.pgm" à "532.pgm".

A.3 : Les fichiers sont des PGM binaires (P5) en niveaux de gris sur 8 bits, de taille 720×720.
Ce n'est pas l'image tel quelle : mpeg2dec met la luminance Y (720×480) en haut, puis les deux
plans de chrominance U et V (360×240 chacun) côte à côte en dessous. La vidéo fait donc 720×480,
8 bits par composante, en 4:2:0 (chroma divisée par 2 en largeur et en hauteur).

A.4 : On a ajouté l'option `-l <fichier>` à mpeg2dec pour écrire les flags de chaque image dans
un fichier de log :

```sh
mpeg2dec -o pgm -l flags.log pendulum.m2v
```

On récupère les flags dans
`info->display_picture->flags` au moment où mpeg2dec sort une image. Exemple de ligne écrite :

```
FRAME 0 type=I progressive_frame=0 top_field_first=1 repeat_first_field=0
```

Ce qui signifie que pour la vidéo du pendulum, les 533 images sont entrelassées, top field first, sans répétition de field.

A.5 : La chroma est d'abord remise à la taille de la luma par interpolation linéaire. On respecte
le placement MPEG-2 : alignée sur les colonnes paires horizontalement, et entre deux lignes de luma
verticalement. On applique ensuite la conversion BT.601 :

    R = 1.164 (Y-16) + 1.596 (V-128)
    G = 1.164 (Y-16) - 0.392 (U-128) - 0.813 (V-128)
    B = 1.164 (Y-16) + 2.017 (U-128)

A.6 : Avec `--ppm <dossier>`, le programme écrit des PPM (P6). Sinon, il affiche dans une
fenetre pygame.

Exemples depuis la racine du projet :

```sh
# Afficher les images à l'écran
uv run --project tvid tvid/main.py data

# Enregistrer les images au format PPM
uv run --project tvid tvid/main.py data --ppm sortie
```

- `data` est le dossier contenant les PGM et le fichier `flags.log`, nécessaire au lecteur actuel.
- `--ppm sortie` écrit les images dans le dossier `sortie`, créé s'il n'existe pas. Sans cette
  option, les images sont affichées à l'écran.

A.7 : Option `--fps N`.

A.8 : mpeg2dec calcule déjà `frame_period` (en unités de 27 MHz) à partir du sequence header.
On l'ajoute simplement au log. Pour pendulum, `frame_period=900900`, donc 27 000 000 / 900 900
= 30 images par seconde.

A.9 : La cadence vient de `--fps` si l'option est donnée, sinon de `frame_period`, sinon on
prend 25 ips. On a vérifié qu'on tient la cadence : environ 29,3 images/s mesurées pour 29,97.

A.10 : Une image entrelacée donne deux images en sortie, une par field, chacune affichée pendant
la moitié de `frame_period`. L'ordre est donné par `top_field_first`, et si `repeat_first_field`
vaut 1 on réaffiche le premier field. Les images marquées progressives ne sont pas désentrelacées.

Pour un field, les lignes de luma sont aux hauteurs 2i (top) ou 2i+1 (bottom). La chroma de chaque
field est aussi décalée : la ligne k est à la hauteur 4k + 0,5 pour le top et 4k + 2,5 pour le
bottom. On interpole à ces positions, ce qui garde luma et chroma alignées pour les deux polarités.
Les flags peuvent être forcés avec `--force-interlaced`, `--force-progressive`, `--tff` et `--bff`.

Résultat sur pendulum : le pendule n'a plus d'effet de peigne, mais on ne voit qu'une lettre sur
deux (O puis K), ce qui clignote. C'est le défaut normal du bob, puisque chaque lettre n'existe que
dans un field.

## B. cnn.ts

B.1 : Le flux vidéo est sur le PID 0x1422 : MPEG-2 544×480 à 29,97 ips.

```sh
ffplay VIDEO/TP/videos/ts/cnn.ts
```

Dans le terminal, la ligne `Stream #0:0[0x1422] ... Video: mpeg2video ...` indique le PID
vidéo entre crochets : `0x1422` (5154 en décimal).

B.2 :
```sh
mpeg2dec -o pgm -l flags.log -t 0x1422 cnn.ts
```

B.3 : En respectant les flags, toute la première moitié (jusqu'à l'image 476 environ) à un effet
de peigne sur ce qui bouge. La deuxième moitié est propre.

B.4 : Sur 845 images, 468 sont marquées `progressive_frame=1`, presque toutes dans la première moitié. Le lecteur ne les désentrelace donc pas. Pourtant, le contenu est entrelacé partout :
l'analyse avec le filtre `idet` de ffmpeg trouve les 845 images entrelacées, en top field first.
Les images sont donc mal signalé.

B.5 : Notre hypothèse est qu'il met `progressive_frame=1` parce qu'il
code l'image entière et non field par field. Or ce flag indique
si le contenu a été capturé en une seule fois ou en deux fields.

B.6 : Le plus simple est d'ignorer les flags et de tout désentrelacer :
`--force-interlaced --tff`. On n'a alors plus de peigne du début à la fin. Une version automatique
consisterait à mesurer l'effet de peigne dans chaque image et à désentrelacer seulement au-dessus
d'un seuil.

## C. ctv.ts

C.1 : Il y a trois programmes vidéo : 100 (vidéo 0x3e9), 101 (0x3f3) et 102 (0x3fd), plus un
programme 150 sans vidéo. Tous sont en 704×480 à 29,97 ips. Le troisième PID vidéo est 0x3fd.

C.2 :
```sh
mpeg2dec -o pgm -l flags.log -t 0x3fd ctv.ts
```

C.3 : Le flux est entrelacé en bottom field first. Au début, un homme fait
glisser un gâteau avec un effet (le gâteau avance tout seul). Pendant cet effet, on voit un effet de peigne sur le gâteau et sur le bras de l'homme.
Avant et après, l'image est propre.

Les images conccernées sont justement marquées `progressive_frame=1`, alors que `idet` les trouve
entrelacées comme le reste. Le plan avec l'effet a surement été retraité au montage dans un
logiciel qui a sorti les images comme progressives, alors que les deux fields correspondent à deux
instants différents.

C.4 : on trouve 0x3e9

C.5 :
```sh
mpeg2dec -o pgm -l flags.log -t 0x3e9 ctv.ts
```

C.6 : C'est un épisode de série tourné comme un film. Les flags changent selon les passages. Les passages marqués progressifs sans répétition correspondent au générique en texte vertical qui défile sur la droite. Le texte a du être incrusté en vidéo par-dessus le film, mais les images sont restés marquées progressives : on voit du peigne sur le texte. L'ordre des fields change aussi en cours de route (bottom first puis top first). Il faut donc bien le relire à chaque image.

## D. Désentrelaceur adaptatif

D.1 : Option `--deint adaptive`, avec `--block` (16 par défaut) et `--threshold` (10 par défaut).

On a vu 2 probleme sur le pendulum :
- Des morceaux du bras du pendule restaient affichés à d'anciennes positions. Si le bras n'est présent
  qu'en t-1, t et t-2 sont pareils à cet endroit, donc le bloc est considéré comme immobile et on
  recopie le bras de t-1. On compare donc aussi t-1 avec t-3 : on n'utilise t-1 que s'il est stable
  lui aussi.
- Des petites encoches restaient sur les bords du bras. Un bloc que le bras ne touche que sur quelques
  pixels a une moyenne trop faible. On élargit donc les zones en mouvement d'un bloc tout autour.

Avec ça, O et K sont affichés ensemble sur 1059 images sur 1066 (0 en bob), et il reste un peu de
peigne sur 5 images. Ces 5 images sont au moment où le pendule fait demi-tour : il repasse au même
endroit, donc t ressemble à t-2 et t-1 à t-3, alors que t-1 et t sont différents. On a essayé de
comparer directement t-1 et t. Sa supprime ce défaut, mais ça casse complètement le test O/K
(une lettre qui existe dans un seul field ressemble à un mouvement), donc on ne l'a pas gardé.

D.2 : L'amélioration est la plus visible sur ce qui est fixe avec des petits détails : textes,
logos, affiches du décor de l'émission de gym. En bob, ces détails sautent d'une ligne à chaque image
et sont plus flous, car on n'a que la moitié des lignes. En adaptatif, ils sont tissés avec le field
précédent donc on retrouve toute la résolution et l'image est stable.

D.3 : Comparaison avec le mode X de VLC sur le programme 102 de `ctv.ts` (PID vidéo `0x3fd`).
Depuis la racine du projet :

```sh
vlc -V xcb_x11 --program=102 --deinterlace=1 --deinterlace-mode=x VIDEO/TP/videos/ts/ctv.ts
```

`--program=102` sélectionne le programme, `--deinterlace=1` active le désentrelacement et
`--deinterlace-mode=x` choisit le mode X (écrit `x` dans la commande).

Pour comparer avec notre lecteur, on extrait d'abord ce même programme dans un dossier séparé :

```sh
mkdir -p data_ctv3
(
    cd data_ctv3
    ../src/mpeg2dec -o pgm -l flags.log -t 0x3fd ../VIDEO/TP/videos/ts/ctv.ts
)
uv run --project tvid tvid/main.py data_ctv3 --deint adaptive --block 16 --threshold 10
```

La comparaison a été effectuée sur des captures d'un court extrait de l'émission de gym,
autour de 70 secondes. Les deux rendus conservent des détails lisibles dans les affiches et
les textes fixes, sans peigne évident sur les captures examinées. Notre rendu apparaît un
peu plus lissé sur certains contours. Ces captures ne permettent pas de conclure sur le
scintillement en lecture ni sur l'ensemble du flux.

Une différence de cadence est également à distinguer : l'export VLC en mode X testé donne
environ 29,97 images/s, tandis que notre adaptatif produit une image par trame entrelacée,
soit environ 59,94 images/s sur ce passage.
