"""
One-off diagnostic: print the raw output of the first few results from a
finished batch, so we can see exactly what Haiku returned. Free to run --
reading results from an already-finished batch doesn't use any tokens.

    python etl/debug_batch.py msgbatch_01R5XfnepBrKM6Sm4rzBfYK1
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic

from config import load_config


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python etl/debug_batch.py <batch_id>")
        sys.exit(1)

    config = load_config()
    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    batch_id = sys.argv[1]

    count = 0
    for entry in client.messages.batches.results(batch_id):
        print("=" * 60)
        print("custom_id:", entry.custom_id)
        print("result.type:", entry.result.type)
        if entry.result.type == "succeeded":
            text = "".join(b.text for b in entry.result.message.content if b.type == "text")
            print("raw text (first 500 chars):")
            print(repr(text[:500]))
        else:
            print("result detail:", entry.result)
        count += 1
        if count >= 5:
            break

    if count == 0:
        print("No results found for this batch ID -- check the ID is correct.")


if __name__ == "__main__":
    main()
