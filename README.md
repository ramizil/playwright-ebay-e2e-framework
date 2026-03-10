# eBay E2E Automation Framework

End-to-end test automation for eBay, built with **Python 3.12**, **Playwright**, and **pytest**. Uses POM + OOP, smart locator strategies, data-driven testing, parallel execution, and CI/CD.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Running Tests](#running-tests)
- [Configuration](#configuration)
- [Data-Driven Testing](#data-driven-testing)
- [Smart Locator System](#smart-locator-system)
- [Retry & Backoff Strategy](#retry--backoff-strategy)
- [Parallel Execution](#parallel-execution)
- [Reporting](#reporting)
- [CI/CD Pipeline](#cicd-pipeline)
- [Docker](#docker)
- [Assumptions & Limitations](#assumptions--limitations)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        TEST LAYER                           │
│  tests/test_shopping_flow.py  ·  tests/test_smoke.py        │
│  - Data-driven parametrisation from JSON                    │
│  - Orchestrates the E2E shopping flow                       │
│  - Allure steps for rich reporting                          │
├─────────────────────────────────────────────────────────────┤
│                      PAGE OBJECTS                           │
│  pages/home_page.py          │  pages/cart_page.py          │
│  pages/search_results_page.py│  pages/product_page.py       │
│  - Each page owns its UI interactions                        │
│  - SmartLocator instances for every element (≥ 2 strategies)│
├─────────────────────────────────────────────────────────────┤
│                       CORE LAYER                            │
│  core/base_page.py       - Smart locator resolution, retry  │
│  core/smart_locator.py   - SmartLocator + LocatorStrategy   │
│  core/retry_handler.py   - Exponential backoff decorator    │
│  core/logger_config.py   - Centralised logging              │
├─────────────────────────────────────────────────────────────┤
│                     UTILITIES                               │
│  utils/data_loader.py        - JSON/YAML loading            │
│  utils/screenshot_manager.py - Screenshot capture + attach  │
│  utils/allure_helper.py      - Allure report enrichment     │
├─────────────────────────────────────────────────────────────┤
│                   CONFIGURATION                             │
│  config/config.yaml      - Timeouts, browsers, retry, URLs  │
│  config/settings.py      - Config loader with env overrides │
│  data/search_data.json   - Test scenarios (data-driven)     │
└─────────────────────────────────────────────────────────────┘
```

### Design Principles

| Principle | Implementation |
|-----------|---------------|
| **POM (Page Object Model)** | Each page has its own class inheriting from `BasePage`. Tests never touch raw selectors. |
| **OOP** | Inheritance (`BasePage` → `HomePage`), locators private to pages, locator resolution via strategy pattern. |
| **SRP** | Each module has one responsibility: `retry_handler` handles retries, `data_loader` handles data, etc. |
| **Data-Driven** | All test inputs come from `data/search_data.json`. Adding a new scenario requires zero code changes. |
| **Smart Locators** | Every element has ≥ 2 locator strategies with automatic fallback. |
| **Resilience** | Retry with exponential backoff, popup/banner handling, graceful skip on missing optional elements. |

---

## Project Structure

```
ebay-e2e-automation/
├── .github/workflows/
│   └── e2e-tests.yml          # GitHub Actions CI/CD pipeline
├── config/
│   ├── config.yaml            # Framework configuration
│   └── settings.py            # Config loader + env overrides
├── core/
│   ├── base_page.py           # Base page with smart locators & retry
│   ├── smart_locator.py       # SmartLocator & LocatorStrategy classes
│   ├── retry_handler.py       # Retry decorator with exponential backoff
│   └── logger_config.py       # Logging setup
├── data/
│   └── search_data.json       # Test scenarios (data-driven)
├── pages/
│   ├── login_page.py          # eBay sign-in page object
│   ├── home_page.py           # eBay home page object
│   ├── search_results_page.py # Search results + price filter + paging
│   ├── product_page.py        # Product detail + variants + add to cart
│   └── cart_page.py           # Shopping cart + total validation
├── tests/
│   ├── conftest.py            # Browser/page fixtures, auto-screenshots
│   ├── test_shopping_flow.py  # Data-driven parametrised E2E test
│   └── test_smoke.py          # Lightweight smoke / sanity test
├── business_steps/
│   ├── __init__.py            # Re-exports all business actions
│   ├── login_actions.py       # login() — Identification
│   ├── search_actions.py      # search_items_by_name_under_price()
│   └── cart_actions.py        # add_items_to_cart(), assert_cart_total_not_exceeds()
├── utils/
│   ├── data_loader.py         # JSON/YAML file loaders
│   ├── screenshot_manager.py  # Screenshot capture utilities
│   └── allure_helper.py       # Allure report attachments
├── models/
│   ├── __init__.py            # Re-exports flow state DTOs
│   └── flow_state.py          # ShoppingFlowState, SmokeFlowState dataclasses
├── gui/
│   ├── app.py                 # Flask-based test runner web UI
│   └── templates/index.html   # Test runner dashboard
├── conftest.py                # Root conftest: logging, settings, hooks
├── requirements.txt           # Python dependencies with pinned versions
├── pyproject.toml             # pytest markers, ruff config
├── Dockerfile                 # Containerised test runner
├── docker-compose.yml         # Multi-browser parallel via Docker
└── README.md                  # This file
```

---

## Quick Start

### Prerequisites

- Python 3.12+
- pip

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd ebay-e2e-automation

# Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
python -m playwright install --with-deps chromium firefox
```

---

## Running Tests

### Run all E2E tests (headless)

```bash
pytest tests/ -v --alluredir=allure-results
```

### Run smoke tests only

```bash
pytest tests/ -v -m smoke --alluredir=allure-results
```

### Run with visible browser (for debugging)

```bash
EBAY_HEADLESS=false pytest tests/ -v -m smoke
```

On Windows PowerShell:

```powershell
$env:EBAY_HEADLESS="false"; pytest tests/ -v -m smoke
```

### Run on a specific browser

```bash
EBAY_BROWSER=firefox pytest tests/ -v --alluredir=allure-results
```

### Run in parallel (multiple workers)

```bash
pytest tests/ -v -n auto --dist=loadfile --alluredir=allure-results
```

---

## Configuration

All configuration lives in `config/config.yaml` and can be overridden by environment variables:

| YAML Key | Env Variable | Default | Description |
|----------|-------------|---------|-------------|
| `base_url` | `EBAY_BASE_URL` | `https://www.ebay.com` | Target site URL |
| `browsers[0]` | `EBAY_BROWSER` | `chromium` | Browser for this session |
| `browser_options.headless` | `EBAY_HEADLESS` | `true` | Headless mode |
| `timeouts.default` | `EBAY_TIMEOUT` | `15000` | Default wait (ms) |
| `logging.level` | `EBAY_LOG_LEVEL` | `INFO` | Log verbosity |

---

## Data-Driven Testing

Test scenarios are defined in `data/search_data.json`:

```json
{
  "test_scenarios": [
    {
      "id": "headphones_under_50",
      "query": "wireless headphones",
      "max_price": 50.00,
      "limit": 5,
      "budget_per_item": 50.00
    }
  ]
}
```

To add a new test case, simply add another object to the `test_scenarios` array. No code changes needed — pytest parametrisation picks it up automatically.

---

## Smart Locator System

Every UI element is defined with **at least 2 locator strategies**:

```python
SEARCH_INPUT = SmartLocator(
    name="search_input",
    strategies=[
        LocatorStrategy("css", "input.gh-tb[type='text']", "by class"),
        LocatorStrategy("xpath", "//input[@name='_nkw']", "by name"),
    ],
)
```

### How it works

1. `BasePage.find_element()` tries Strategy #1 (primary).
2. If it times out → logs the failure → tries Strategy #2 (fallback).
3. If all strategies fail → takes a screenshot → raises `SmartLocatorError`.
4. Every attempt is logged with the strategy description and attempt number.

### Supported locator methods

| Method | Playwright API | Example |
|--------|---------------|---------|
| `css` | `page.locator(selector)` | `input#gh-btn` |
| `xpath` | `page.locator("xpath=...")` | `//input[@name='_nkw']` |
| `text` | `page.get_by_text(text)` | `Add to cart` |
| `role` | `page.get_by_role(role, ...)` | `button, name=Search` |
| `test_id` | `page.get_by_test_id(id)` | `ux-call-to-action` |
| `placeholder` | `page.get_by_placeholder(text)` | `Search for anything` |
| `label` | `page.get_by_label(text)` | `Quantity` |

---

## Retry & Backoff Strategy

The `@with_retry` decorator wraps any function with exponential backoff:

```python
@with_retry(max_attempts=3, backoff_factor=1.0)
def click_add_to_cart(self):
    element = self.find_element(self.ADD_TO_CART_BUTTON)
    element.click()
```

**Backoff formula**: `wait = backoff_factor × 2^(attempt-1) ± 25% jitter`

| Attempt | Wait (approx.) |
|---------|----------------|
| 1 | 0 s (first try) |
| 2 | ~1 s |
| 3 | ~2 s |

---

## Parallel Execution

### Option 1: pytest-xdist (recommended)

```bash
pytest tests/ -n auto --dist=loadfile
```

- Each worker gets an isolated browser context (no shared state).
- `--dist=loadfile` keeps parametrised variants of the same test on one worker.

### Option 2: Docker Compose (multi-browser)

```bash
docker-compose up --build
```

Launches separate containers for Chromium and Firefox simultaneously.

### Session Isolation

Each test gets its own `BrowserContext` with:
- Independent cookies and local storage
- Separate viewport and locale settings
- Its own Playwright trace recording

---

## Reporting

### Allure Reports

```bash
# Run tests with Allure output
pytest tests/ -v --alluredir=allure-results

# Generate and open the report
allure serve allure-results
```

Features:
- **Steps**: Each action (search, filter, add-to-cart) appears as a named step.
- **Attachments**: Screenshots, traces, and test data attached automatically.
- **Environment**: Browser name, base URL, and framework version shown on overview.
- **Parametrisation**: Each data-driven scenario has its own entry.

### HTML Reports (per-run folders)

Each test run generates self-contained HTML reports in a unique folder:

```
reports/run_20260310_133737/
    smoke_test_20260310_133900.html
    summary_20260310_133737.html
screenshots/run_20260310_133737/
    smoke_01_home_20260310_133756.png
```

Reports embed screenshots as base64, so they can be shared as standalone files.

### Install Allure CLI

```bash
# macOS
brew install allure

# Windows (Scoop)
scoop install allure

# Linux
sudo apt-get install allure
```

---

## CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/e2e-tests.yml`):

1. **Matrix strategy**: Runs tests on Chromium and Firefox in parallel.
2. **Artifact uploads**: Allure results, screenshots, and traces are saved.
3. **Report generation**: Merges results from all browsers into one report.
4. **GitHub Pages**: Deploys the Allure report on pushes to `main`.

### Trigger manually

Go to Actions → E2E Tests → Run workflow.

---

## Docker

### Build and run

```bash
docker build -t ebay-e2e .
docker run --rm \
  -v $(pwd)/allure-results:/app/allure-results \
  -v $(pwd)/screenshots:/app/screenshots \
  -e EBAY_BROWSER=chromium \
  ebay-e2e
```

### Multi-browser with Docker Compose

```bash
docker-compose up --build --abort-on-container-exit
```

---

## Core Functions

### `searchItemsByNameUnderPrice(query, max_price, limit)`

Searches eBay, applies price filters, collects qualifying item URLs with pagination support.

### `addItemsToCart(urls)`

Opens each product URL, selects random variants (size/colour), clicks "Add to Cart", captures evidence.

### `assertCartTotalNotExceeds(budget_per_item, items_count)`

Navigates to cart, reads the subtotal, asserts `total ≤ budget_per_item × items_count`.

---

## Assumptions & Limitations

| Area | Assumption |
|------|-----------|
| **Authentication** | Tests run as a **guest user**. eBay allows browsing and adding to cart without login. A login stub can be added by extending `HomePage` with a `login()` method. |
| **Currency** | Prices are assumed to be in **USD ($)**. The price parser looks for `$` symbols. For other currencies, extend `_parse_price()` in the page objects. |
| **Bot Detection** | eBay may occasionally show CAPTCHAs or rate-limit automated browsers. Running headless with realistic viewport/locale settings mitigates this, but it's not guaranteed. |
| **Auction Items** | The framework filters to **"Buy It Now"** listings to ensure items can be added to cart. Auction-only items are skipped. |
| **Item Variants** | When size/colour is required, a **random** option is selected. This exercises different code paths but makes test outcomes non-deterministic for specific variant coverage. |
| **Cart Persistence** | eBay may require login to persist cart across sessions. Guest carts are session-scoped. |
| **Parallel Safety** | Each test gets an isolated `BrowserContext` — no shared cookies or state. Safe for `-n auto`. |
| **Logging** | Log lines include clickable source references (`File "path", line N`) for PyCharm console navigation. |
