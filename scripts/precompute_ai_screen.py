"""Screen every cart in the masked sample with the AI and save the results with the app.

Usage (from the app folder, with the virtual environment active and OPENAI_API_KEY in .env):
    python scripts/precompute_ai_screen.py

What it does:
  1. Loads the masked sample in demo_data/ and applies the same rules as the app.
  2. Retrieves Governance Guide / rule-spec passages for each cart (embeddings).
  3. Sends each cart in scope (approved, non-cancelled, not #welfare) to the chat model
     with the purchase-justification prompt. Carts already screened with the current
     prompt version and model are reused, so re-running only fills gaps.
  4. Writes precomputed/ai_screen_results.json. Commit and push that file so the
     deployed app shows results without anyone clicking "Screen" or spending API credit.

Re-run it whenever the prompt (PROMPT_VERSION), the chat model or the sample data changes.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys
import time

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from govlens import justification as js  # noqa: E402
from govlens.config import get_api_key  # noqa: E402
from govlens.demo import load_masked_sample  # noqa: E402
from govlens.engine import analyse  # noqa: E402
from govlens.knowledge import build_retriever  # noqa: E402
from govlens.models import CHAT_MODEL, EMBEDDING_MODEL  # noqa: E402


def main() -> None:
    api_key = get_api_key()
    if not api_key:
        sys.exit("OPENAI_API_KEY not found in the environment or .env. Nothing was screened.")
    _, orders, detail, _ = analyse(*load_masked_sample())
    items = js.add_price_bands(js.build_items(orders, detail))
    cart_ids = js.eligible_carts(items)["Cart_ID"].tolist()
    cache = js.ScreenCache()
    done = js.cached_results(items, cart_ids, CHAT_MODEL, cache)
    todo = [c for c in cart_ids if c not in done]
    print(f"{len(cart_ids)} carts in scope; {len(done)} already screened with {js.PROMPT_VERSION}; {len(todo)} to screen.")

    errors: dict[str, str] = {}
    if todo:
        retriever = build_retriever(api_key, EMBEDDING_MODEL)
        print(f"Retrieval: {retriever.description}")
        start = time.time()

        def progress(n: int, total: int) -> None:
            if n == total or n % 25 == 0:
                print(f"  screened {n}/{total} ({time.time() - start:.0f}s)")

        new, errors = js.screen_carts(items, todo, api_key, CHAT_MODEL, cache, progress=progress, retriever=retriever)
        done.update(new)
        if errors:
            print(f"{len(errors)} cart(s) failed; re-run the script to retry them:")
            for cart_id, message in list(errors.items())[:10]:
                print(f"  {cart_id}: {message}")

    count = js.write_bundle(done, items, CHAT_MODEL)
    tiers = Counter(
        js.combined_tier(items, c, str(items.loc[items["Cart_ID_Effective"] == c, "Reason_For_Purchase"].iloc[0]),
                         done[c])["Tier"]
        for c in done
    )
    print(f"Wrote {count} results to {js.BUNDLE_PATH.relative_to(APP_DIR)}")
    print("Purchase-justification tiers: " + ", ".join(f"{t} {n}" for t, n in tiers.most_common()))
    print("Next: commit and push precomputed/ai_screen_results.json so the deployed app uses these results.")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
