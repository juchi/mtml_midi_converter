# MTML — Music Text Markup Language
**Format de notation musicale textuelle pour génération IA → MIDI**
Version 1.0

---

## Vue d'ensemble

MTML est un format texte hiérarchique et lisible conçu pour représenter des compositions musicales complètes ou partielles. Il est optimisé pour la génération par LLM et la conversion automatique vers MIDI.

**Principes fondateurs :**
- Chaque ligne commence par un mot-clé (pas d'ambiguïté grammaticale)
- Les paramètres sont en paires `clé=valeur`
- Tout champ non reconnu est ignoré silencieusement (extensible)
- Les commentaires (`#`) sont autorisés partout

---

## Structure globale

Un fichier MTML est composé de blocs imbriqués dans cet ordre canonique :

```
@SONG       ← (1) Un seul bloc global obligatoire
  @TRACK    ← (N) Un ou plusieurs tracks
    @BAR    ← (M) Une ou plusieurs mesures par track
      N / CHORD / CC / REST   ← événements
```

---

## 1. Bloc `@SONG` — En-tête global

Déclare les paramètres globaux de la composition. **Obligatoire, unique, en première ligne.**

```
@SONG tempo=<bpm> time=<num>/<den> key=<tonalité> ppq=<ticks> [bars=<n>] [title="<texte>"]
```

### Paramètres

| Paramètre | Type | Obligatoire | Description |
|-----------|------|-------------|-------------|
| `tempo` | entier | oui | Battements par minute (ex. `120`) |
| `time` | fraction | oui | Signature rythmique (ex. `4/4`, `3/4`, `6/8`) |
| `key` | string | oui | Tonalité (ex. `Cmaj`, `Amin`, `F#maj`, `Bbmin`) |
| `ppq` | entier | oui | Ticks par noire (résolution). Valeur recommandée : `480` |
| `bars` | entier | non | Nombre total de mesures (informatif) |
| `title` | string | non | Titre de la composition |

### Exemple

```
@SONG tempo=120 time=4/4 key=Cmaj ppq=480 bars=8 title="Étude en Do"
```

---

## 2. Bloc `@TRACK` — Piste instrument

Déclare une piste MIDI. **Un `@TRACK` par instrument.** Les tracks sont indépendantes et jouées simultanément.

```
@TRACK id=<identifiant> ch=<1-16> program=<0-127> [name="<texte>"] [vol=<0-127>] [pan=<0-127>]
```

### Paramètres

| Paramètre | Type | Obligatoire | Description |
|-----------|------|-------------|-------------|
| `id` | string | oui | Identifiant unique de la track (ex. `piano`, `bass`, `drums`) |
| `ch` | entier 1–16 | oui | Canal MIDI. **Canal 10 réservé aux percussions GM** |
| `program` | entier 0–127 | oui | Numéro de programme GM (instrument). Voir table GM ci-dessous |
| `name` | string | non | Nom affiché dans le DAW |
| `vol` | entier 0–127 | non | Volume initial (CC7). Défaut : `100` |
| `pan` | entier 0–127 | non | Panoramique (CC10). Centre : `64`, gauche : `0`, droite : `127` |

### Programmes GM fréquents

| Program | Instrument | Program | Instrument |
|---------|------------|---------|------------|
| `0` | Acoustic Grand Piano | `32` | Acoustic Bass |
| `25` | Acoustic Guitar (steel) | `33` | Electric Bass (finger) |
| `40` | Violin | `48` | String Ensemble 1 |
| `56` | Trumpet | `73` | Flute |
| `0` (ch=10) | Percussions GM | — | — |

### Exemple

```
@TRACK id=piano ch=1 program=0 name="Grand Piano" vol=90 pan=64
@TRACK id=bass ch=2 program=32 name="Fingered Bass" vol=85 pan=40
@TRACK id=drums ch=10 program=0 name="Drums" vol=100 pan=64
```

---

## 3. Bloc `@BAR` — Mesure

Regroupe les événements d'une mesure. **Contenu dans un `@TRACK`.**

```
@BAR <numéro> [chord=<symbole>] [time=<num>/<den>]
```

### Paramètres

| Paramètre | Type | Obligatoire | Description |
|-----------|------|-------------|-------------|
| `<numéro>` | entier | oui | Numéro de mesure, commence à `1` |
| `chord` | string | non | Accord de référence de la mesure (ex. `Cmaj`, `G7`, `Dm7`, `F#dim`) |
| `time` | fraction | non | Signature locale (si différente du `@SONG`) |

### Exemple

```
@BAR 1 chord=Cmaj
@BAR 5 chord=G7 time=3/4
```

---

## 4. Événements — Notes et silences

### 4.1 Note : `N`

Événement de note unique.

```
N <pitch> <duration> <velocity> [options]
```

#### Pitch — Hauteur

Format : `<note><altération><octave>`

- Notes : `C D E F G A B`
- Altérations : `#` (dièse), `b` (bémol). Pas de double altération.
- Octave : entier, `C4` = Do médium (MIDI 60)

Exemples valides : `C4`, `F#3`, `Bb5`, `G2`, `A#4`, `Eb6`

#### Duration — Durée

Valeurs symboliques (relatives à la signature du `@SONG`) :

| Valeur | Nom | Durée relative |
|--------|-----|----------------|
| `4` | Ronde | 4 noires |
| `2` | Blanche | 2 noires |
| `1` | Noire | 1 noire |
| `1/2` | Croche | 1/2 noire |
| `1/4` | Double croche | 1/4 noire |
| `1/8` | Triple croche | 1/8 noire |
| `1.5` | Noire pointée | 1,5 noire |
| `3/4` | Croche pointée | 3/4 noire |

Ou en ticks absolus : `t240` (= 1/2 noire à 480 PPQ)

#### Velocity — Vélocité

Entier `0–127`. Références indicatives :
- `pp` → `30–40` | `p` → `50–60` | `mp` → `65–75`
- `mf` → `80–90` | `f` → `100–110` | `ff` → `115–127`

#### Options facultatives

| Option | Description | Exemple |
|--------|-------------|---------|
| `tie` | Lie cette note à la suivante (même pitch) | `N C4 1 80 tie` |
| `bend=<cents>` | Pitch bend en centièmes (−200 à +200) | `N E4 1 75 bend=+50` |
| `cc<n>=<val>` | Control Change inline sur cette note | `N G3 2 90 cc7=64` |

#### Notes simultanées (polyphonie)

Plusieurs notes jouées en même temps sont séparées par `|` sur la même ligne :

```
N C4 1 80 | N E4 1 75 | N G4 1 70
```

#### Exemple complet

```
@BAR 1 chord=Cmaj
  N C4 1   80 | N E4 1   75 | N G4 1   70
  N D4 1/2 70
  N E4 1/2 68
  N C4 1   85 tie
@BAR 2 chord=Cmaj
  N C4 1   85
```

---

### 4.2 Accord : `CHORD`

Génère automatiquement un accord à partir de son symbole. Le parser déduit les notes selon la voix standard (position fondamentale, octave 4 par défaut).

```
CHORD <symbole> <duration> <velocity> [voicing=<type>] [oct=<n>]
```

#### Symboles d'accords supportés

| Suffixe | Type | Exemple |
|---------|------|---------|
| *(aucun)* | Majeur | `C`, `F#` |
| `maj` | Majeur | `Cmaj` |
| `min` ou `m` | Mineur | `Amin`, `Am` |
| `7` | Dominante 7e | `G7` |
| `maj7` | Majeur 7e | `Cmaj7` |
| `m7` | Mineur 7e | `Dm7` |
| `dim` | Diminué | `Bdim` |
| `aug` | Augmenté | `Eaug` |
| `sus2` / `sus4` | Suspendu | `Gsus4` |
| `9`, `m9`, `maj9` | 9e | `C9` |
| `/X` | Basse spécifique | `G7/B`, `C/E` |

#### Options

| Option | Valeurs | Description |
|--------|---------|-------------|
| `voicing` | `close` (défaut), `open`, `drop2` | Disposition des voix |
| `oct` | entier | Octave de la fondamentale (défaut : `4`) |

#### Exemple

```
@BAR 3 chord=Dm7
  CHORD Dm7 2 75
  CHORD G7  2 78
```

---

### 4.3 Silence : `REST`

```
REST <duration>
```

Exemple :

```
REST 1/2
```

---

### 4.4 Control Change : `CC`

Envoie un message MIDI Control Change, positionné en ticks dans la mesure.

```
CC <numéro> <valeur> [t<position>]
```

- `<position>` : position en ticks depuis le début de la mesure (défaut : `t0`)

#### CC fréquents

| N° | Nom |
|----|-----|
| `1` | Modulation wheel |
| `7` | Volume |
| `10` | Pan |
| `11` | Expression |
| `64` | Sustain pedal (0=off, 127=on) |

#### Exemple

```
@BAR 4
  CC 64 127 t0
  N C4 2 80
  CC 64 0 t480
```

---

## 5. Percussions GM (canal 10)

Sur le canal 10, le pitch ne désigne pas une hauteur mais un type de percussion :

| Pitch MIDI | Note MTML | Percussion |
|------------|-----------|------------|
| 35 | `B1` | Acoustic Bass Drum |
| 36 | `C2` | Bass Drum 1 |
| 38 | `D2` | Acoustic Snare |
| 42 | `F#2` | Closed Hi-Hat |
| 46 | `Bb2` | Open Hi-Hat |
| 49 | `C#3` | Crash Cymbal 1 |
| 51 | `Eb3` | Ride Cymbal 1 |

#### Exemple groove basique

```
@TRACK id=drums ch=10 program=0 name="Drums"
  @BAR 1
    N C2  1   100 | N F#2 1/2 80
    N F#2 1/2 75
    N D2  1   95  | N F#2 1/2 80
    N F#2 1/2 75
```

---

## 6. Commentaires

Le caractère `#` en début ou milieu de ligne introduit un commentaire ignoré au parsing.

```
# Ceci est un commentaire
@BAR 1 chord=Cmaj  # commentaire inline
  N C4 1 80        # do médium, forte
```

---

## 7. Règles de parsing

1. **Mot-clé obligatoire en début de ligne** (après espaces optionnels) : `@SONG`, `@TRACK`, `@BAR`, `N`, `CHORD`, `REST`, `CC`
2. **Lignes vides ignorées**
3. **Commentaires ignorés** (de `#` à fin de ligne)
4. **Clés inconnues ignorées** silencieusement (forward-compatibility)
5. **Ordre canonique** : `@SONG` → `@TRACK` → `@BAR` → événements
6. **Polyphonie** : `|` sépare des notes simultanées sur une même ligne ; elles partagent position et durée déclarées
7. **Position dans la mesure** : les événements s'enchaînent séquentiellement, la position courante avançant de la durée de chaque événement (ou du maximum en cas de polyphonie `|`)

---

## 8. Exemple complet

```
# Exemple MTML — 8 mesures, 2 instruments
@SONG tempo=100 time=4/4 key=Cmaj ppq=480 bars=8 title="Simple étude"

@TRACK id=piano ch=1 program=0 name="Grand Piano" vol=88 pan=64

  @BAR 1 chord=Cmaj
    N C4 1 80 | N E4 1 75 | N G4 1 70
    N C4 1 85

  @BAR 2 chord=G7
    N G3 1 78 | N B3 1 74 | N D4 1 70 | N F4 1 66
    N G3 1 80

  @BAR 3 chord=Amin
    N A3 1 76 | N C4 1 72 | N E4 1 70
    N A3 1 78

  @BAR 4 chord=F
    N F3 1 75 | N A3 1 70 | N C4 1 68
    N F3 1 77

  @BAR 5 chord=Cmaj
    N C4 1/2 82 | N E4 1/2 78
    N D4 1/2 75
    N E4 1/2 78
    N C4 1   85

  @BAR 6 chord=G7
    N G4 1/2 80
    N F4 1/2 76
    N D4 1/2 73
    N B3 1   79

  @BAR 7 chord=Amin
    N A3 2 78 | N C4 2 74 | N E4 2 70
    REST 2

  @BAR 8 chord=Cmaj
    N C4 4 90 | N E4 4 85 | N G4 4 80

@TRACK id=bass ch=2 program=32 name="Fingered Bass" vol=85 pan=40

  @BAR 1 chord=Cmaj
    N C2 1 100
    N C2 1 95

  @BAR 2 chord=G7
    N G1 1 98
    N G1 1 95

  @BAR 3 chord=Amin
    N A1 1 97
    N A1 1 93

  @BAR 4 chord=F
    N F1 1 98
    N C2 1 95

  @BAR 5 chord=Cmaj
    N C2 1 100
    N E2 1/2 90
    N G2 1/2 88

  @BAR 6 chord=G7
    N G1 1   100
    N D2 1/2 90
    N F2 1/2 88

  @BAR 7 chord=Amin
    N A1 2 98
    N E2 2 92

  @BAR 8 chord=Cmaj
    N C2 4 100
```

---

## 9. Erreurs et récupération

Le parser doit adopter une stratégie de **récupération souple** :

- **Ligne non reconnue** → log d'avertissement, ligne ignorée, parsing continue
- **Paramètre manquant obligatoire** → valeur par défaut si possible, sinon bloc ignoré
- **Pitch invalide** → note ignorée, warning
- **Duration invalide** → durée = `1` (noire) par défaut, warning
- **Velocity hors [0-127]** → clampée à `0` ou `127`

---

## 10. Conversion en ticks MIDI

```
ticks = duration_value × ppq

Exemples à ppq=480 :
  Ronde (4)    → 4 × 480 = 1920 ticks
  Blanche (2)  → 2 × 480 = 960 ticks
  Noire (1)    → 1 × 480 = 480 ticks
  Croche (1/2) → 0.5 × 480 = 240 ticks
  Double croche (1/4) → 0.25 × 480 = 120 ticks
```

La position absolue d'un événement dans le fichier MIDI = `(bar - 1) × ticks_per_bar + position_dans_mesure`

```
ticks_per_bar = (num / den) × 4 × ppq
Exemple 4/4 à ppq=480 : (4/4) × 4 × 480 = 1920 ticks par mesure
Exemple 3/4 à ppq=480 : (3/4) × 4 × 480 = 1440 ticks par mesure
```

---

*Fin de la spécification MTML v1.0*
