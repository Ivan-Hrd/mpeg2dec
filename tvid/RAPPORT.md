# TP TVID : décompression et affichage de flux vidéo

Outils utilisés :
- mpeg2dec, modifié pour ajouter une option `-l <fichier>` qui écrit les infos du sequence header
  (taille, `frame_period`, `progressive_sequence`) puis une ligne par image décodée avec ses flags.
  Les lignes sont numérotées comme les fichiers `N.pgm`.
- `main.py`, notre lecteur en Python (numpy + pygame) : conversion en RGB, sortie PPM ou écran,
  cadence, désentrelacement bob et adaptatif.
- `verif.py`, quelques mesures pour vérifier les résultats sans tout regarder à l'oeil.

## A. Flux MPEG-2 élémentaire

**A.1.** On a choisi `pendulum.m2v`. (à compléter : ce qu'on voit dans vlc)

**A.2.**
```sh
mpeg2dec -o pgm -l flags.log pendulum.m2v
```
On obtient 533 images, de `0.pgm` à `532.pgm`.

**A.3.** Les fichiers sont des PGM binaires (`P5`) en niveaux de gris sur 8 bits, de taille 720×720.
Ce n'est pas l'image telle quelle : mpeg2dec met la luminance Y (720×480) en haut, puis les deux
plans de chrominance U et V (360×240 chacun) côte à côte en dessous. La vidéo fait donc 720×480,
8 bits par composante, en 4:2:0 (chroma divisée par 2 en largeur et en hauteur).

**A.4.** On récupère les flags dans `info->display_picture->flags` au moment où mpeg2dec sort une
image. Exemple :
```
FRAME 0 type=I progressive_frame=0 top_field_first=1 repeat_first_field=0
```
Sur pendulum, les 533 images sont entrelacées, top field first, sans répétition de field.

**A.5.** La chroma est d'abord remise à la taille de la luma par interpolation linéaire. On respecte
le placement MPEG-2 : alignée sur les colonnes paires horizontalement, et entre deux lignes de luma
verticalement. On applique ensuite la conversion BT.601 :

    R = 1.164 (Y-16) + 1.596 (V-128)
    G = 1.164 (Y-16) - 0.392 (U-128) - 0.813 (V-128)
    B = 1.164 (Y-16) + 2.017 (U-128)

**A.6.** Avec `--ppm <dossier>`, le programme écrit des PPM (`P6`). Sinon, il affiche dans une
fenêtre pygame.

**A.7.** Option `--fps N`.

**A.8.** mpeg2dec calcule déjà `frame_period` (en unités de 27 MHz) à partir du sequence header.
On l'ajoute simplement au log. Pour pendulum, `frame_period=900900`, soit 27 000 000 / 900 900
= 29,97 images par seconde.

**A.9.** La cadence vient de `--fps` si l'option est donnée, sinon de `frame_period`, sinon on
prend 25 ips. On a vérifié qu'on tient la cadence : environ 29,3 images/s mesurées pour 29,97.

**A.10.** Une image entrelacée donne deux images en sortie, une par field, chacune affichée pendant
la moitié de `frame_period`. L'ordre est donné par `top_field_first`, et si `repeat_first_field`
vaut 1 on réaffiche le premier field. Les images marquées progressives ne sont pas désentrelacées.

Pour un field, les lignes de luma sont aux hauteurs 2i (top) ou 2i+1 (bottom). La chroma de chaque
field est aussi décalée : la ligne k est à la hauteur 4k + 0,5 pour le top et 4k + 2,5 pour le
bottom. On interpole à ces positions, ce qui garde luma et chroma alignées pour les deux polarités.
Les flags peuvent être forcés avec `--force-interlaced`, `--force-progressive`, `--tff` et `--bff`.

Résultat sur pendulum : le pendule n'a plus d'effet de peigne, mais on ne voit qu'une lettre sur
deux (O puis K), ce qui clignote. C'est le défaut normal du bob, puisque chaque lettre n'existe que
dans un field. (à compléter : comparaison avec vlc en mode bob)

## B. cnn.ts

**B.1.** Le flux vidéo est sur le PID 0x1422 (5154) : MPEG-2 544×480 à 29,97 ips.

**B.2.**
```sh
mpeg2dec -o pgm -l flags.log -t 0x1422 cnn.ts
```

**B.3.** En respectant les flags, toute la première moitié (jusqu'à l'image 476 environ) a un effet
de peigne sur ce qui bouge. La deuxième moitié est propre.

**B.4.** Sur 845 images, 468 sont marquées `progressive_frame=1`, presque toutes dans la première
moitié. Le lecteur ne les désentrelace donc pas. Pourtant, le contenu est entrelacé partout :
l'analyse avec le filtre `idet` de ffmpeg trouve les 845 images entrelacées, en top field first.
Les images sont donc mal signalées. (à compléter : comparaison avec vlc en mode bob)

**B.5.** On lit `progressive_sequence=0`. (à compléter : l'énoncé parle du cas où il vaut 1, à
vérifier.) Notre hypothèse sur l'erreur de l'encodeur : il met `progressive_frame=1` parce qu'il
code des frame pictures, c'est-à-dire l'image entière et non field par field. Or ce flag indique
si le contenu a été capturé en une seule fois ou en deux fields.

**B.6.** Le plus simple est d'ignorer les flags et de tout désentrelacer :
`--force-interlaced --tff`. On n'a alors plus de peigne du début à la fin. Une version automatique
consisterait à mesurer l'effet de peigne dans chaque image et à désentrelacer seulement au-dessus
d'un seuil.

## C. ctv.ts

**C.1.** Il y a trois programmes vidéo : 100 (vidéo 0x3e9), 101 (0x3f3) et 102 (0x3fd), plus un
programme 150 sans vidéo. Tous sont en 704×480 à 29,97 ips. Le troisième PID vidéo est 0x3fd.
(à vérifier : l'ordre dans ffplay)

**C.2.**
```sh
mpeg2dec -o pgm -l flags.log -t 0x3fd ctv.ts
```

**C.3.** Le flux est entrelacé en bottom field first. Au début, une scène de série : un homme fait
glisser un gâteau vers une fillette, avec un effet spécial (le gâteau avance tout seul). Pendant cet
effet, des images 75 à 190, on voit un effet de peigne sur le gâteau et sur le bras de l'homme.
Avant et après, l'image est propre.

Ces images 75 à 190 sont justement marquées `progressive_frame=1`, alors que `idet` les trouve
entrelacées comme le reste. On pense que le plan avec l'effet a été retraité au montage dans un
logiciel qui a sorti les images comme progressives, alors que les deux fields correspondent à deux
instants différents. Le lecteur les tisse donc sans les désentrelacer. Mesure de l'effet de peigne :
2,1 % des pixels pendant l'effet, contre 0,15 à 0,5 % autour. En forçant l'entrelacé, on retombe à
1,05 %. (à compléter : comparaison avec vlc)

**C.4.** Le premier PID vidéo est 0x3e9.

**C.5.**
```sh
mpeg2dec -o pgm -l flags.log -t 0x3e9 ctv.ts
```

**C.6.** C'est un épisode de série tourné comme un film. Les flags changent selon les passages :

| Images | Flags | Contenu (idet) |
|---|---|---|
| 4-826, 2817-3559 | progressif, repeat_first_field une image sur deux | progressif |
| 827-1183, 1489-1805 | progressif | entrelacé (bottom first) |
| 1184-1344 | entrelacé, bottom first | entrelacé, bottom first |
| 2338-2514, 3864-4021 | entrelacé, top first | entrelacé, top first |

- Les passages progressifs avec `repeat_first_field` sont du film en 3:2 pulldown. Les flags suivent
  le motif (progressive, tff, rff) = 101, 110, 111, 100, ... : 4 images de film donnent 10 fields,
  ce qui fait passer de 23,976 à 29,97 ips.
- Les passages marqués progressifs sans répétition correspondent au générique en texte vertical qui
  défile sur la droite. Le texte a dû être incrusté en vidéo par-dessus le film, mais les images sont
  restées marquées progressives : on voit du peigne sur le texte.
- L'ordre des fields change aussi en cours de route (bottom first puis top first). Il faut donc bien
  le relire à chaque image.

## D. Désentrelaceur adaptatif

**D.1.** Option `--deint adaptive`, avec `--block` (16 par défaut) et `--threshold` (10 par défaut).
Pour chaque field t :
1. on découpe l'image en blocs ;
2. pour chaque bloc, on calcule la différence moyenne de luma entre t et t-2 (même polarité) ;
3. si elle dépasse le seuil, le bloc bouge et on le désentrelace en bob ;
4. sinon on fait un weave : les lignes manquantes sont prises dans le field t-1.

Deux problèmes sont apparus sur pendulum :
- Des morceaux du bras du pendule restaient affichés à d'anciennes positions. Si le bras n'est présent
  qu'en t-1, t et t-2 sont pareils à cet endroit, donc le bloc est considéré comme immobile et on
  recopie le bras de t-1. On compare donc aussi t-1 avec t-3 : on n'utilise t-1 que s'il est stable
  lui aussi.
- Des petites encoches restaient sur les bords du bras. Un bloc que le bras ne touche que sur quelques
  pixels a une moyenne trop faible. On élargit donc les zones en mouvement d'un bloc tout autour.

Avec ça, O et K sont affichés ensemble sur 1059 images sur 1066 (0 en bob), et il reste un peu de
peigne sur 5 images. Ces 5 images sont au moment où le pendule fait demi-tour : il repasse au même
endroit, donc t ressemble à t-2 et t-1 à t-3, alors que t-1 et t sont différents. On a essayé de
comparer directement t-1 et t. Ça supprime ce défaut, mais ça casse complètement le test O/K
(une lettre qui existe dans un seul field ressemble à un mouvement), donc on ne l'a pas gardé.

**D.2.** L'amélioration est la plus visible sur ce qui est fixe avec des petits détails : textes,
logos, affiches du décor de l'émission de gym. En bob, ces détails sautent d'une ligne à chaque image
et sont plus flous, car on n'a que la moitié des lignes. En adaptatif, ils sont tissés avec le field
précédent : on retrouve toute la résolution et l'image est stable. Mesure de la différence moyenne
entre deux images successives (images 2000 à 2060) : 6,7 en bob contre 1,7 en adaptatif sur l'image
entière, et 8,0 contre 0,9 sur une affiche fixe.

**D.3.**
```sh
vlc --program=<prog> --deinterlace-mode X ctv.ts
```
(à compléter)
