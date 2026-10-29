# Camtoshop

**From camera to shop.** A small merchant talks about a product on their phone, mistakes included. Camtoshop turns that one video into everything needed to sell it:

- **An edited Reel**, directed by an AI agent. It removes failed takes and self-corrections, puts word-by-word captions where they never cover the product, adds giant text behind the speaker, product-in-use cutaways and an end card with the price. Then it **watches its own render and fixes it**.
- **Studio catalog photos** made from the real product, not a lookalike.
- **A bilingual store listing** (English first, plus the video's language) with title, description, key points, SEO and price.
- **Three Meta ad variants** (benefit, story, offer), with copy and a designed creative.
- **One-click publishing** to a **Shopify** store, the **Meta catalog** (Instagram & Facebook Shops, WhatsApp catalog) and **Instagram Reels**.

Built solo for the Meta Global AI Developer Hackathon (Oct 27 – Nov 4, 2026), Startup track. **All code in this repository was written during the hackathon**; see the commit history.

## Meta models, and what each one does

| Step | Model |
|---|---|
| Watch and listen to the raw video: product, brand, label text, language, best frame | **Muse Spark 1.3** |
| Speech to text with vocabulary biasing for brand names | **Muse Voice Transcribe** |
| Word-level timestamps (forced alignment on the transcript) | **wav2vec2 XLSR-53** (Meta open weights) |
| Pick the clean takes: drop restarts, "sorry, I made a mistake", stutters | **Muse Spark** |
| Direct the Reel: hook, giant on-screen claims, cutaways, emphasized words, end card | **Muse Spark** (agent) |
| Review the finished Reel and send a corrected direction | **Muse Spark** (agent loop) |
| Track the product (boxes) and cut out speaker + product (masks) frame by frame | **SAM 3.1** + `meta-sam-parser` |
| Catalog photos, cover shot, product-in-use scenes, end card, ad creatives | **Muse Image** (edits from the SAM cutout) |
| Listing and ad copy, in several languages | **Muse Spark** |
| Publish the product and the Reel | **Meta Graph API** (Catalog `items_batch`, Instagram Reels resumable upload) |

## How the agent works

1. **Montage** (once per video): Voice Transcribe → XLSR alignment → Spark picks word ranges to keep → cut list. SAM tracks the product.
2. **Direction**: Spark proposes the graphics for the chosen *look* (`directo`, `anuncio`, `premium`). Domain rules clamp the proposal: at most 2 giant-text moments, cutaways never over the spoken hook, no overlaps.
3. **Render**: ffmpeg + Pillow. Alternating punch-in zooms centered on the product hide jump cuts. Giant text is drawn between the background and the SAM mask of speaker + product, sized and placed so the key word is never hidden. HLG HDR from iPhone is graded to SDR, and the voice is cleaned and leveled to −14 LUFS.
4. **Review loop**: Spark watches the finished Reel. If the hook is weak, a price is hidden or a cutaway is off, it returns a corrected direction and the Reel is rendered again.
5. **Merchant requests**: "make it calmer" → Spark rewrites the direction and may switch the look.

## Architecture

Hexagonal (ports and adapters), so models and channels can be swapped without touching business rules.

```
camtoshop/
  dominio/       Pure business rules and use cases: cuts, captions, direction, listing, ads, publishing
  adaptadores/   Meta Model API, SAM masks, XLSR, ffmpeg render, Shopify, Meta catalog, Instagram
  aplicacion/    Orchestrates a project: parallel steps, progress, persisted state
  web/           Thin FastAPI routes + a single-page UI (English / Spanish)
tests/           Domain tests with fake adapters (no network, no credits)
```

## Run it

Requires Python 3.12, ffmpeg and a Meta Model API key.

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt fastapi "uvicorn[standard]" python-multipart
export MODEL_API_KEY=...            # Meta Model API
.venv/bin/uvicorn camtoshop.web.app:app --port 8765
# open http://127.0.0.1:8765 and drop a product video
.venv/bin/python -m pytest          # domain tests
```

### Connecting the sales channels (optional)

Each channel turns on when its variables exist (environment or macOS Keychain):

| Channel | Variables |
|---|---|
| Shopify | `SHOPIFY_TIENDA` (`mystore.myshopify.com`), `SHOPIFY_TOKEN` (custom app with `write_products`, `write_files`, `write_publications`) |
| Meta catalog | `META_CATALOGO_ID`, `META_TOKEN` (system user with `catalog_management`) |
| Instagram | `IG_USUARIO_ID`, `META_TOKEN` (with `instagram_content_publish`) |

Shopify publishes first, so the Meta catalog item can link to the live product page and its CDN images.

## Credits

Barlow Condensed font: SIL Open Font License (see `camtoshop/assets/fonts/OFL.txt`).
