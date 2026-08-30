# suth-test-app

A deliberately bad single-page UI, used only as a fixture to exercise [suth](..)
end to end. Not a real product.

## What's bad about it (on purpose)

- The `≡` header button and every `♡` save button are icon-only with no
  `aria-label` and no visible text label — a synthetic user is supposed to
  hesitate/declare confusion here, per the `impatient-mobile-shopper-v2`
  persona's forbidden assumption about icons.
- The filter panel's "Apply" button shows a spinner that never resolves and
  never actually filters the listings — a dead click / silent failure.

## Running it

```bash
python3 -m http.server 8765
```

Then point `suth_config.json`'s `base_url` (or its `dev` environment overlay)
at `http://localhost:8765`.

## Suggested objective

"Filter the listings to find one under $50,000."
