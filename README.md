# ShuMao
ShuMao (书猫, lit. book cat) is an English-Chinese dictionary website inspired by MDBG.
Unlike most online dictionaries, ShuMao is open-source and does not rely on external network services, allowing it to be self-hosted for privacy or reliability concerns.

## Technical Architecture
ShuMao is powered by a Python Flask web server which serves a vanilla HTML/CSS/JS frontend.
Dictionary entries are queried from a SQLite database combining data from multiple text file sources (e.g. CC-CEDICT).

## Resources
[CC-CEDICT](https://www.mdbg.net/chinese/dictionary?page=cc-cedict): Chinese-English dictionary

[Hanzi Writer](https://hanziwriter.org/): Stroke order animations

[HanziLookup](https://github.com/gugray/hanzi_lookup): Chinese handwriting recognition

[Tatoeba](https://tatoeba.org/): Example translated sentences

[HSK 3.0 Vocabulary](https://github.com/ivankra/hsk30): HSK 3.0 word tagging

[jieba](https://github.com/fxsjy/jieba): Chinese word segmentation