# Pali Text Society (PTS) & GRETIL Edition in Markdown

This repository contains the complete **Pali Text Society (PTS)** edition of the Pāḷi Tipiṭaka and commentaries, along with all additional Pāḷi literature from **GRETIL** (Göttingen Register of Electronic Texts in Indian Languages), converted into clean, structured **Markdown**.

The PTS digital texts were originally digitized and proofread by the Dhammakaya Foundation (Thailand, 1989–1996) in collaboration with the Pali Text Society, and hosted by the Göttingen State and University Library at [GRETIL](https://gretil.sub.uni-goettingen.de/gretil.html#Pali).

---

## Corpus & Directory Structure

All texts are split by **Sutta, Chapter, Vagga, and Book** into **372 Markdown documents** across the following hierarchy:

```text
.
├── vinaya/                       # Vinayapiṭaka (31 files)
│   ├── mv01.md - mv10.md         # Mahāvagga (10 Khandhakas)
│   ├── cv01.md - cv12.md         # Cullavagga (12 Khandhakas)
│   ├── vb-pj.md                  # Suttavibhaṅga 1: Pārājikakaṇḍa
│   ├── vb-ss.md                  # Suttavibhaṅga 1: Saṃghādisesa
│   ├── vb-ay.md                  # Suttavibhaṅga 1: Aniyata
│   ├── vb-np.md                  # Suttavibhaṅga 1: Nissaggiyapācittiya
│   ├── vb-pc.md                  # Suttavibhaṅga 2: Pācittiya
│   ├── vb-pd.md                  # Suttavibhaṅga 2: Pāṭidesanīya
│   ├── vb-sk.md                  # Suttavibhaṅga 2: Sekhiyavatta
│   ├── vb-bi.md                  # Suttavibhaṅga 2: Bhikkhunīvibhaṅga
│   └── parivara.md               # Parivārapāḷi
│
├── sutta/                        # Suttantapiṭaka (275 files)
│   ├── dn/                       # Dīghanikāya (34 files: dn01.md - dn34.md)
│   ├── mn/                       # Majjhimanikāya (152 files: mn001.md - mn152.md)
│   ├── sn/                       # Saṃyuttanikāya (56 files: sn01.md - sn56.md)
│   ├── an/                       # Aṅguttaranikāya (11 files: an01.md - an11.md)
│   └── kn/                       # Khuddakanikāya (22 files)
│       ├── khp.md                # Khuddakapāṭha
│       ├── dhp.md                # Dhammapada
│       ├── ud.md                 # Udāna
│       ├── iti.md                # Itivuttaka
│       ├── snp.md                # Suttanipāta
│       ├── vv.md                 # Vimānavatthu
│       ├── pv.md                 # Petavatthu
│       ├── thag.md               # Theragāthā
│       ├── thig.md               # Therīgāthā
│       ├── jat01.md - jat06.md   # Jātaka (Volumes 1–6)
│       ├── mnd.md                # Mahāniddesa
│       ├── cnd.md                # Cūḷaniddesa
│       ├── ps01.md, ps02.md      # Paṭisambhidāmagga (Volumes 1 & 2)
│       ├── ap.md                 # Apadāna
│       ├── bv.md                 # Buddhavaṃsa
│       └── cp.md                 # Cariyāpiṭaka
│
├── abhidhamma/                   # Abhidhammapiṭaka (28 files)
│   ├── dhs.md                    # Dhammasaṅgaṇī
│   ├── vbh01.md - vbh18.md       # Vibhaṅga (18 Vibhaṅgas)
│   ├── dhk.md                    # Dhātukathā
│   ├── pug.md                    # Puggalapaññatti
│   ├── kvu.md                    # Kathāvatthu
│   ├── yam01.md, yam02.md        # Yamaka (Volumes 1 & 2)
│   ├── pat-duka.md               # Dukapaṭṭhāna
│   └── pat-tika1.md - pat-tika3.md # Tikapaṭṭhāna (Volumes 1–3)
│
├── paracanonical/                # Paracanonical Works (3 files)
│   ├── milindapanha.md           # Milindapañha (PTS edition)
│   ├── petakopadesa.md           # Peṭakopadesa
│   └── nettippakarana.md         # Nettippakaraṇa
│
├── chronicles/                   # Chronicles / Vaṃsa (4 files)
│   ├── dathavamsa.md             # Dāṭhāvaṃsa
│   ├── dipavamsa.md              # Dīpavaṃsa
│   ├── hatthavanagalla.md        # Hatthavanagallavihāravaṃsa
│   └── mahavamsa.md              # Mahāvaṃsa
│
├── commentary/                   # Aṭṭhakathā / Commentaries (8 files)
│   ├── visuddhimagga.md          # Buddhaghosa: Visuddhimagga (PTS edition)
│   └── samantapasadika-01.md - 07.md # Buddhaghosa: Samantapāsādikā (Vols 1–7)
│
├── treatises/                    # Grammatical, Poetical & Extra Treatises (23 files)
│   ├── grammar/                  # Pāḷi Grammars (Kaccāyana, Moggallāna, Saddanīti, etc.)
│   ├── poetry/                   # Jinacarita, Jinavaṃsadīpa, Telakaṭāhagāthā
│   ├── lexicon/                  # Abhidhānappadīpikā
│   ├── rhetoric/                 # Subodhālaṅkāra
│   └── suanco/                   # Lokappadīpasāra, Upāsakajanālaṅkāra
│
├── .github/workflows/
│   └── sync-upstream.yml         # Automated weekly upstream sync GitHub Action
├── convert.py                    # Deterministic conversion & sync script
└── README.md
```

---

## Document Formatting

* **Print Page Markers & Anchors:** Each page from the original printed PTS edition has an anchor `<a id="page-XXX"></a>` and sub-header `##### *[PTS Page XXX]*` for exact citation matching.
* **Critical Apparatus & Variant Readings:** Footnotes and manuscript variants are extracted into Markdown footnotes (`[^pXXX-Y]`) linking to an aggregated `## Footnotes` section at the end of each document.
* **Clean Paragraphs & Verses:** Original line-break hyphens across print lines (e.g. `paṭi-panno`) are rejoined into standard Pāḷi words, with prose flowing continuously and poetic verses formatted cleanly.
* **Standard Latin Diacritics:** Pure IAST Pali Roman Unicode (`ā`, `ī`, `ū`, `ṭ`, `ḍ`, `ṇ`, `ḷ`, `ñ`, `ṅ`, `ṃ`).

---

## Running the Deterministic Converter

[`convert.py`](file:///Users/christie/Repositories/Pali/pts/convert.py) is a standalone deterministic Python script using standard libraries and SHA-256 caching.

### 1. Sync and convert latest upstream changes
```bash
python3 convert.py --sync
```
*(Automatically shallow/sparse-clones `INDOLOGY/GRETIL-mirror:main`, checks file hashes in `.cache/manifest.json`, and updates only modified files).*

### 2. Convert from an existing local copy
```bash
python3 convert.py --source /path/to/gretil/2_pali
```

### 3. Force rebuild all files
```bash
python3 convert.py --force
```

### Command Line Flags:
* `--sync`: Automatically clone or pull latest main from the upstream repository.
* `--upstream-repo`: URL of the upstream repository (default: `https://github.com/INDOLOGY/GRETIL-mirror.git`).
* `--upstream-dir`: Local storage directory for upstream checkout (default: `.cache/gretil-mirror`).
* `--source`: Path to GRETIL `2_pali` directory.
* `--output`: Output directory for generated Markdown files (default: `.`).
* `--force`: Force complete rebuild, bypassing SHA-256 cache.
* `--manifest`: Path to manifest cache file (default: `.cache/manifest.json`).

---

## Continuous Sync (GitHub Actions)

A GitHub Actions workflow is provided at [`.github/workflows/sync-upstream.yml`](file:///Users/christie/Repositories/Pali/pts/.github/workflows/sync-upstream.yml). It runs on a weekly schedule (and can be triggered manually via `workflow_dispatch`), syncing with upstream changes and committing updates automatically.
