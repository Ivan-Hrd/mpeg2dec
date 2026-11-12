# TP TVID : décompression et affichage de flux vidéo

Outils utilisés :
- mpeg2dec, modifié pour ajouter une option `-l <fichier>` qui écrit les infos du sequence header
  (taille, `frame_period`, `progressive_sequence`) puis une ligne par image décodée avec ses flags.
  Les lignes sont numérotées comme les fichiers `N.pgm`.
- `main.py`, notre lecteur en Python (numpy + pygame) : conversion en RGB, sortie PPM ou écran,
  cadence, désentrelacement bob et adaptatif.
- `verif.py`, quelques mesures pour vérifier les résultats sans tout regarder à l'oeil.
- `compare_vlc.py`, capture du rendu de libVLC sans fenêtre, pour comparer bob et X sur
  de courts extraits. Les captures et les logs sont dans `../output/validation/`.

Les commandes ci-dessous utilisent le binaire recompilé `../src/mpeg2dec` (depuis `tvid`).
Il faut lancer le décodage dans un dossier de sortie distinct pour chaque flux, avec les chemins
absolus du binaire et de la vidéo (voir le README).

## A. Flux MPEG-2 élémentaire

**A.1.** On a choisi `pendulum.m2v`. La séquence montre un pendule en mouvement et les lettres
O et K. Les deux fields correspondent à des instants différents : sans désentrelacement,
le pendule présente des dents de peigne. En bob, le mouvement est décomposé en deux sorties
par image source, mais les lettres alternent, car chacune appartient à un seul field.

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
prend 25 ips, y compris si la valeur est absente du log. Une cadence forcée doit être positive
et finie. Le lecteur utilise des échéances absolues sur une horloge monotone pour éviter
d'accumuler les erreurs d'attente. Il ne peut toutefois tenir cette cadence que si le calcul
et l'affichage sont assez rapides. En bob, 29,97 images sources/s demandent 59,94 sorties/s.
Les tests vérifient la priorité des paramètres et les durées, sans prétendre garantir les
performances de toutes les machines.
Après réduction des copies de tableaux et calcul parallèle des deux rendus bob, l'essai sur
120 sorties donne 2,00 s, soit 59,94 sorties/s. Il utilise le pilote SDL `dummy`, sans fenêtre :
il valide la cadence du calcul et du planificateur sur cette machine, sans mesurer le coût
d'une fenêtre réelle sur le bureau.

**A.10.** Une image entrelacée donne deux images en sortie, une par field, chacune affichée pendant
la moitié de `frame_period`. L'ordre est donné par `top_field_first`, et si `repeat_first_field`
vaut 1 dans une séquence entrelacée on réaffiche le premier field. Les images marquées progressives
ne sont pas désentrelacées, sauf si l'utilisateur force l'entrelacé. `progressive_sequence=1`
est également pris en compte. Le log ajoute `nb_fields`, calculé par libmpeg2, pour représenter
les durées de répétition, y compris dans une séquence progressive. Une image progressive est
affichée pendant `nb_fields / 2` périodes de base, sans créer de mouvement artificiel.

Pour un field, les lignes de luma sont aux hauteurs 2i (top) ou 2i+1 (bottom). La chroma de chaque
field est aussi décalée : la ligne k est à la hauteur 4k + 0,5 pour le top et 4k + 2,5 pour le
bottom. On interpole à ces positions, ce qui garde luma et chroma alignées pour les deux polarités.
Les flags peuvent être forcés avec `--force-interlaced`, `--force-progressive`, `--tff` et `--bff`.

Résultat sur pendulum : le pendule n'a plus d'effet de peigne, mais on ne voit qu'une lettre sur
deux (O puis K), ce qui clignote. C'est le défaut normal du bob, puisque chaque lettre n'existe que
dans un field. La capture de VLC 3.0.20 en bob confirme cette alternance : deux sorties successives
montrent K puis O, et le pendule n'a plus de peigne visible. Le bob de VLC ne préserve donc
pas non plus les deux lettres simultanément. Les interpolations des deux lecteurs peuvent
différer sur les contours ; on compare le comportement, pas une égalité pixel à pixel.

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
l'analyse multi-image avec le filtre `idet` de ffmpeg classe les 845 images en top field first.
Ce détecteur est une heuristique, mais son résultat et le peigne observé concordent : des images
contenant deux instants sont signalées progressives. Sur les sources 0 à 469, notre indicateur
de peigne passe de 2,18 % à 1,25 % en forçant le bob TFF ; sur 480 à 839, il reste à 1,01 %.
Les captures VLC en bob forcé sur un extrait du début ne montrent plus les dents de peigne
du rendu tissé. Les détails fins peuvent toujours contribuer à l'indicateur, même sans entrelacement.

**B.5.** On lit `progressive_sequence=0` dans le fichier fourni. L'énoncé explique la signification
de la valeur 1 ; il n'affirme pas que CNN a nécessairement cette valeur. Une séquence marquée 0
peut contenir des images progressives et entrelacées : ce flag seul ne prouve donc aucune erreur.
L'anomalie se situe ici dans `progressive_frame`. Une explication possible est une confusion
entre une *frame picture* (structure de codage de l'image entière) et un contenu progressif
(un même instant pour toutes les lignes). Une frame picture peut parfaitement contenir deux
fields d'instants différents. La cause exacte dans l'encodeur reste une hypothèse.

**B.6.** Le plus simple est d'ignorer les flags et de tout désentrelacer :
`--force-interlaced --tff`. On supprime ainsi le tissage des deux instants sur les passages mal
signalés. Une version automatique
consisterait à mesurer l'effet de peigne dans chaque image et à désentrelacer seulement au-dessus
d'un seuil.

## C. ctv.ts

**C.1.** Il y a trois programmes vidéo : 100 (vidéo 0x3e9), 101 (0x3f3) et 102 (0x3fd), plus un
programme 150 sans vidéo. Les trois vidéos sont en 704×480, avec une période de base de
900900 ticks (29,97 ips). En prenant l'ordre des programmes de la table PAT (100, 101, 102),
le troisième PID vidéo est 0x3fd. L'ordre des indices de streams affichés par ffmpeg peut différer :
il faut se fier au numéro de programme et au PID, pas à l'indice `Stream #0:n`.

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
logiciel qui a signalé les images comme progressives, alors que les deux fields correspondent à deux
instants différents. C'est une hypothèse sur le montage, pas une information démontrée par le flux.
Le lecteur les tisse donc sans les désentrelacer. Sur les mêmes sources 90 à 179, l'indicateur de
peigne vaut 2,12 % avec les flags et 1,06 % en forçant le bob BFF ; il vaut 0,16 % sur 30 à 69
et 0,53 % sur 200 à 259. Les captures de VLC en bob forcé confirment la disparition des dents
de peigne sur le bras et le gâteau. Ce résultat ne répare pas d'éventuels défauts déjà présents
dans les images montées.

**C.4.** Le premier PID vidéo est 0x3e9.

**C.5.**
```sh
mpeg2dec -o pgm -l flags.log -t 0x3e9 ctv.ts
```

**C.6.** C'est un épisode de série tourné comme un film. Les flags changent selon les passages :

| Images (exemples de passages) | Signalisation dominante | Estimation du contenu |
|---|---|---|
| 4-826, 2817-3559 | principalement progressif, répétitions de fields | principalement progressif / film |
| 827-1183, 1489-1805 | principalement progressif, sans répétition | mélange film / incrustations entrelacées |
| 1184-1344 | entrelacé, bottom first | entrelacé, bottom first |
| 2338-2514, 3864-4021 | principalement entrelacé, top first | entrelacé, top first |

- Les passages progressifs avec `repeat_first_field` correspondent à du film en 3:2 pulldown.
  Dans les portions régulières, les combinaisons (progressive, tff, rff) alternent entre
  101, 110, 111 et 100 (la phase dépend du point de départ) : 4 images de film donnent 10 fields,
  ce qui fait passer de 23,976 à 29,97 ips.
- Les passages marqués progressifs sans répétition correspondent au générique en texte vertical qui
  défile sur la droite. Le texte a dû être incrusté en vidéo par-dessus le film, mais les images sont
  restées marquées progressives : on voit du peigne sur le texte.
- L'ordre des fields change aussi en cours de route (bottom first puis top first). Il faut donc bien
  le relire à chaque image.

Les intervalles du tableau ne sont pas des segments parfaitement homogènes : par exemple,
4 à 826 comprend aussi cinq images signalées entrelacées. Le détecteur `idet` confirme le
caractère mixte du flux (1541 sorties classées progressives, 1391 TFF, 1089 BFF et une indéterminée
en détection multi-image), sans permettre d'attribuer avec certitude une origine à chaque pixel.

## D. Désentrelaceur adaptatif

**D.1.** Option `--deint adaptive`, avec `--block` (16 par défaut) et `--threshold` (10 par défaut).
Pour chaque field t :

1. on découpe le field en blocs (16 colonnes × 16 lignes de field par défaut), en conservant
   les blocs incomplets au bord ;
2. pour chaque bloc, on calcule la différence moyenne de luma entre t et t-2 (même polarité) ;
3. si elle dépasse le seuil, le bloc bouge et on le désentrelace en bob ;
4. sinon on fait un weave : les lignes manquantes sont prises dans le field t-1.

L'historique est réinitialisé lorsque l'alternance top/bottom est rompue (changement d'ordre
ou répétition), ainsi qu'au changement de séquence. Il faut trois fields de référence avant
de pouvoir choisir weave ; en attendant, le lecteur utilise bob. Le rendu weave conserve
également les deux polarités séparées lors de la reconstruction de la chroma.

Deux problèmes sont apparus sur pendulum :

- Des morceaux du bras du pendule restaient affichés à d'anciennes positions. Si le bras n'est présent
  qu'en t-1, t et t-2 sont pareils à cet endroit, donc le bloc est considéré comme immobile et on
  recopie le bras de t-1. On compare donc aussi t-1 avec t-3 : on n'utilise t-1 que s'il est stable
  lui aussi.
- Des petites encoches restaient sur les bords du bras. Un bloc que le bras ne touche que sur quelques
  pixels a une moyenne trop faible. On élargit donc les zones en mouvement d'un bloc tout autour.

Avec ça, le test détecte O et K ensemble sur 1059 sorties sur 1066 (0 en bob), et l'indicateur
de peigne dépasse 0,2 % sur la zone du pendule dans 5 sorties. Le critère temporel reste sensible
aux demi-tours et aux mouvements périodiques : t peut ressembler à t-2 et t-1 à t-3, alors que
t-1 et t diffèrent. Comparer directement deux fields de polarités différentes risque en revanche
de classer les lettres O/K comme du mouvement, alors qu'elles appartiennent à une image fixe.

**D.2.** L'amélioration est la plus visible sur ce qui est fixe avec des petits détails : textes,
logos, affiches du décor de l'émission de gym. En bob, ces détails sautent d'une ligne à chaque image
et sont plus flous, car on n'a que la moitié des lignes. En adaptatif, ils sont tissés avec le field
précédent : on retrouve toute la résolution et l'image est stable. Mesure de la différence moyenne
entre deux sorties successives (sources 2000 à 2059 incluses) : 6,7 en bob contre 1,7 en adaptatif sur l'image
entière, et 8,0 contre 0,9 sur une affiche fixe.

**D.3.** On sélectionne le programme 102, correspondant au PID 0x3fd :
```sh
vlc --program=102 --deinterlace=1 --deinterlace-mode=x ctv.ts
```
Le nom accepté par VLC 3.0.20 est `x` en minuscule. Les captures du passage de l'émission de gym
montrent que X conserve les détails des panneaux et des caractères, contrairement à la perte
de résolution verticale du bob. C'est aussi l'intérêt du weave dans les zones fixes de notre
adaptatif. Les deux algorithmes ne sont pas identiques : notre décision par blocs avec un seuil
simple reste sensible aux mouvements périodiques et aux frontières des zones en mouvement.
Une capture fixe ne suffit pas à comparer la fluidité ; la mesure temporelle de D.2 complète
l'examen des images pour notre lecteur.

## Vérification et limites des mesures

Les décodages ont été relancés avec le binaire recompilé : 533 images pour pendulum, 845 pour
CNN, 4420 pour CTV 0x3fd et 4022 pour CTV 0x3e9. Les mesures de `verif.py` sélectionnent
désormais le même intervalle d'images sources dans chaque mode, avant de générer les sorties.
Le calcul est effectué progressivement pour éviter de conserver toute la vidéo en mémoire.

L'indicateur nommé « peigne » compte les pixels dont la luma s'écarte de ses deux lignes
voisines dans le même sens, avec un produit des écarts supérieur à 400. Ce n'est pas une
mesure absolue de l'entrelacement : des caractères et des textures fines peuvent le déclencher.
De même, `idet` fournit une estimation, pas la vérité sur l'origine de chaque image.
Les différences de comptage entre décodeurs et les décalages dus aux coupes sur des images clés
interdisent d'assimiler automatiquement leurs numéros d'images.

Les sept tests de `test_main.py` couvrent la cadence et son repli, les répétitions, les blocs
incomplets, les changements de polarité, la chroma en weave et l'association PGM/flags.
Les captures libVLC servent de référence visuelle ; elles ne constituent pas une comparaison
pixel à pixel des filtres.
