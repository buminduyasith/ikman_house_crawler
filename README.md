# ikman-house-crawler

Fetches house-for-sale listings from Ikman (Sri Lanka) and sends them to a Telegram group.

## What this does

- Crawls Ikman SERP pages (supports sorting + pagination via query params).
- Extracts listing data from the embedded `window.initialData` JSON.
- Maps listings into Python dataclasses (`IkmanAd`).
- Sends each listing to a Telegram group using `sendMediaGroup` (an album of photos), with a caption containing:
  - title
  - price
  - description
  - details

## Requirements

- Python 3.13+
- `uv`
- A Telegram bot token (from @BotFather)
- A Telegram group chat id (the group where the bot is added)

## Setup

1. Create a `.env` file

Copy the sample env file and edit it:

```bash
cp .env.sample .env
```

Fill in at minimum:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

2. Run with `uv`

```bash
uv run python main.py
```

## Configuration (environment variables)

All config is read from `.env` (if present) and from your shell environment.

- `TELEGRAM_BOT_TOKEN` (required)
  - Bot token from @BotFather.
- `TELEGRAM_CHAT_ID` (required)
  - Target group id (often starts with `-100...`).
- `IKMAN_URL` (optional)
  - Base URL to crawl. You can include sorting/filter params.
  - Example:
    - `https://ikman.lk/en/ads/sri-lanka/houses-for-sale?sort=date&order=desc&buy_now=0&urgent=0`
- `START_PAGE` (optional, default: `1`)
  - First page to crawl.
- `PAGES` (optional, default: `1`)
  - Number of pages to crawl.
- `PRICE_MAX` (optional)
  - If set, only ads with `price <= PRICE_MAX` (in LKR) are sent.
  - Example: `PRICE_MAX=20000000`
- `SEND_LIMIT` (optional)
  - Limits how many ads are sent per run (useful for testing).
- `MAX_IMAGES` (optional, default: `10`)
  - Number of images per listing to include in the Telegram album.
  - Telegram media groups allow up to 10 items.
- `LOG_LEVEL` (optional, default: `INFO`)
  - `DEBUG`, `INFO`, `WARNING`, `ERROR`

## Project structure

- `main.py`
  - Entry point.
  - Loads `.env`, crawls `PAGES` pages, de-duplicates ads by `ad.id`, applies `PRICE_MAX` filter, then sends to Telegram.
- `house_crawler.py`
  - Fetches SERP HTML, extracts `window.initialData` JSON, maps ads into `IkmanAd`.
  - Contains `build_paged_url()` to keep query params and set the `page=` parameter.
- `models.py`
  - Dataclasses: `IkmanAd`, `Images`, `Category`.
- `telegram_sender.py`
  - Telegram API integration.
  - Uses `sendMediaGroup` and builds captions in Markdown.

## Notes for developers

- **Token safety**: do not commit `.env`. It is ignored by `.gitignore`.
- **Telegram limits**:
  - `sendMediaGroup` supports max 10 media items.
  - Only the first media item can have a caption.
- **Price parsing**:
  - `PRICE_MAX` filtering extracts digits from strings like `Rs 75,000,000`.
  - Ads without a parseable price are skipped when `PRICE_MAX` is enabled.
- **De-duplication**:
  - Ads are de-duplicated by `ad.id` across pages.
- **Ikman changes**:
  - The crawler relies on `window.initialData` being present in the HTML.
  - If Ikman changes their frontend, update `_extract_window_initial_data()` and the JSON path.
