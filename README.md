# Camtoshop

**The AI community manager that lives in WhatsApp.** A merchant sends a product photo to one WhatsApp line. Minutes later the Reel comes back with **Publish / Change / Discard** buttons, and one tap posts it to *their own* Instagram. Every morning the agent suggests what to promote next, and it learns from the results of the merchant's real Reels.

No app to learn, no filming, no editor: the merchant already knows how to use WhatsApp.

## How a merchant uses it

1. **Sign up** at the portal, connect Instagram + Facebook Page (and Shopify, if they have it) and link the phones they'll use: the portal gives a one-time code and the merchant sends it to the line, which proves the number is theirs.
2. **Send a product**: 1–8 photos with what it is and the price, or a voice note. Camtoshop recognizes the merchant by phone number and asks only for what's missing.
3. **Approve**: the Reel arrives in the chat. *Publish* is tied to that exact version; *Change* takes a plain-language request ("calmer", "another hook") and invalidates the old approval.
4. **Every morning** the agent proposes the product that has gone longest without promotion. With enough data it compares hook styles on real Instagram results and applies the winner, and it says why. With too little data it draws no conclusion.

**Trust is the product.** Nothing is published without the merchant's tap. Prices come only from the merchant or the store, never from the model. Unsupported promises are removed. AI scenes start from the real product cutout and are labeled as AI. Each merchant's tokens are encrypted, and webhooks without a valid Meta signature are rejected.

## Beyond WhatsApp

**From camera to shop.** A small merchant talks about a product on their phone, mistakes included. Camtoshop turns that one video into everything needed to sell it:

- **An edited Reel**, directed by an AI agent. It removes failed takes and self-corrections, puts word-by-word captions where they never cover the product, adds giant text behind the speaker, product-in-use cutaways and an end card with the price. Then it **watches its own render and fixes it**.
- **Studio catalog photos** made from the real product, not a lookalike.
- **A bilingual store listing** (English first, plus the video's language) with title, description, key points, SEO and price.
- **Three Meta ad variants** (benefit, story, offer), with copy and a designed creative.
- **One-click publishing** to a **Shopify** store, the **Meta catalog** (Instagram & Facebook Shops, WhatsApp catalog) and **Instagram Reels**.

**No video? No problem.** Camtoshop also builds the Reel from **a few photos** (plus a short message and, optionally, a voice note) or **straight from the products already in a Shopify store**: SAM 3.1 cuts out the real product, Muse Spark writes the script, Muse Image places the *same* product in a lifestyle scene, and the product moves in layers over its own photo with giant text behind it. Nobody has to film anything.

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

## Three ways in, one engine

| Input | What happens |
|---|---|
| **Talking video** | The full editing pipeline below. |
| **1–8 photos + message** (+ optional voice note) | Spark identifies the product → SAM cuts it out of each photo → Spark writes hook, 3 benefits and call to action → Muse Image makes a lifestyle scene from the real cutout (labeled as AI) → layered render → Spark reviews and rewrites the script if needed. The voice note becomes the Reel's voice. |
| **Shopify store** | Pick up to 6 products; each one becomes a photo Reel using the store's own photos, description and price. |

**Trust rules in the domain** (tested): the price only comes from the merchant or the store, never from the model; promises like free shipping, warranty, organic or discounts are removed unless the merchant said them; AI scenes always start from the real product cutout; nothing is published without the merchant's click, and stores get drafts by default.

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

## Brand kit

Each merchant sets a logo, colors, lettering, look (Bold, Color, Clean) and music in the portal. Every Reel follows them, and any Reel can be rendered again with another look without calling the AI models. The three music tracks are composed from scratch by `scripts/hacer_musica.py`, so they carry no third-party rights; merchants can upload their own. Instagram's music library is not available through the publishing API.

## What runs where

The merchant flow (WhatsApp, photo and Shopify Reels, portal, daily agent) is deployed on **Cloud Run**, scaling to zero, with data on a Cloud Storage volume and Cloud Scheduler for the morning proposal. The talking-video pipeline needs local alignment models and runs in the local setup.

During the hackathon the line uses Meta's WhatsApp test number, limited to 5 verified recipients, and the Meta app isn't reviewed yet, so only accounts with a role in the app can connect Instagram.

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
| Instagram | `IG_USUARIO_ID`, `META_TOKEN` (with `instagram_content_publish`; the system user needs the Facebook Page linked to the Instagram account). Optional `IG_TOKEN` overrides it with an Instagram Login token |

Shopify publishes first, so the Meta catalog item can link to the product page and its CDN images.

**Safe by default:** products are created as **drafts** in Shopify and as **hidden** (`staging`) items in the Meta catalog, so Camtoshop can be used on a real merchant's store without anything going live until they review it. Set `CAMTOSHOP_EN_VIVO=si` to publish directly.

## Credits

Barlow Condensed font: SIL Open Font License (see `camtoshop/assets/fonts/OFL.txt`).
