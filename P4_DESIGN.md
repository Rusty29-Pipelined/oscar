# OSCAR P-4 — Human-Approved Alerts

P-4 turns scan rows into readable alerts and keeps the decision with the user. It does not place orders.

Each alert contains symbol, timeframe, setup family, entry, stop, T-1/T-2/T-3, risk/reward, state and reason codes. Delivery providers can later consume the text file or JSON without changing the scanner.

Initial delivery is a local alert file. Email, ntfy, Pushover or Chartink webhooks can be added as adapters. Automatic broker execution is explicitly outside P-4.
