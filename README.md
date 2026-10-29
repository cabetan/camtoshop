# Camtoshop

**From camera to shop.** Film your product once on your phone and get everything you need to sell it: an edited Reel, studio catalog photos, ad variants, and a live listing.

Built for the Meta Global AI Developer Hackathon (Oct 27 – Nov 4, 2026). All code in this repository was written during the hackathon.

## Meta models used

| Step | Model |
|---|---|
| Understand the raw video (best take, product, attributes, copy) | Muse Spark |
| Track the product frame by frame | SAM 3.1 |
| Studio catalog photo from the real cutout | Muse Image |
| Speech to text | Muse Voice Transcribe |

## Architecture

Hexagonal (ports and adapters): business rules live in `camtoshop/dominio`, Meta Model API and other services live in `camtoshop/adaptadores`.

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install requests pytest
export MODEL_API_KEY=...   # your Meta Model API key
```
