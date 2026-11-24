# Recorded desk replies

The desk's replies to the reference solution's read-only calls, exactly as the desk serves them (written by generate.py from the desk's own code and data; in no room). The notes are in notes.md.

## find_instrument {"query": "LQVB"}

{"query": "LQVB", "count": 1, "listings": [{"symbol": "LQVB", "name": "Lindqvist Bearings AB", "exchange": "NRX", "currency": "SEK", "listing": "primary", "lot_size": 100, "tick_size": 0.05}]}

## find_instrument {"query": "EKVN"}

{"query": "EKVN", "count": 1, "listings": [{"symbol": "EKVN", "name": "Ekvarn Telecom AB", "exchange": "NRX", "currency": "SEK", "listing": "primary", "lot_size": 100, "tick_size": 0.05}]}

## find_instrument {"query": "KZNP"}

{"query": "KZNP", "count": 1, "listings": [{"symbol": "KZNP", "name": "Kazenami Precision Co", "exchange": "KTX", "currency": "JPY", "listing": "primary", "lot_size": 100, "tick_size": 5}]}

## find_instrument {"query": "VXMR"}

{"query": "VXMR", "count": 1, "listings": [{"symbol": "VXMR", "name": "Vexmoor Logistics Inc", "exchange": "WSX", "currency": "USD", "listing": "primary", "lot_size": 10, "tick_size": 0.01}]}

## find_instrument {"query": "KAFO"}

{"query": "KAFO", "count": 1, "listings": [{"symbol": "KAFO", "name": "Kauppila Foods Oyj", "exchange": "ESX", "currency": "EUR", "listing": "primary", "lot_size": 10, "tick_size": 0.02}]}

## find_instrument {"query": "BKQM"}

{"query": "BKQM", "count": 1, "listings": [{"symbol": "BKQM", "name": "Brekke Marine AB", "exchange": "NRX", "currency": "SEK", "listing": "primary", "lot_size": 50, "tick_size": 0.02}]}

## find_instrument {"query": "PLHA"}

{"query": "PLHA", "count": 1, "listings": [{"symbol": "PLHA", "name": "Pellham Analytics Inc", "exchange": "WSX", "currency": "USD", "listing": "primary", "lot_size": 10, "tick_size": 0.01}]}

## find_instrument {"query": "RTSY"}

{"query": "RTSY", "count": 1, "listings": [{"symbol": "RTSY", "name": "Rautio Systems Oyj", "exchange": "ESX", "currency": "EUR", "listing": "primary", "lot_size": 25, "tick_size": 0.02}]}

## get_calendar {"exchange": "ESX", "start_date": "2026-11-13", "end_date": "2026-11-30"}

{"exchange": "ESX", "name": "Eastsea Exchange", "start_date": "2026-11-13", "end_date": "2026-11-30", "trading_days": ["2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20", "2026-11-23", "2026-11-24", "2026-11-25", "2026-11-26", "2026-11-27", "2026-11-30"], "closed_weekdays": []}

## get_calendar {"exchange": "KTX", "start_date": "2026-11-13", "end_date": "2026-11-30"}

{"exchange": "KTX", "name": "Kaito Exchange", "start_date": "2026-11-13", "end_date": "2026-11-30", "trading_days": ["2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20", "2026-11-24", "2026-11-25", "2026-11-26", "2026-11-27", "2026-11-30"], "closed_weekdays": [{"date": "2026-11-23", "reason": "Labour Thanksgiving Day"}]}

## get_calendar {"exchange": "NRX", "start_date": "2026-11-13", "end_date": "2026-11-30"}

{"exchange": "NRX", "name": "Northern Exchange", "start_date": "2026-11-13", "end_date": "2026-11-30", "trading_days": ["2026-11-13", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20", "2026-11-23", "2026-11-24", "2026-11-25", "2026-11-26", "2026-11-27", "2026-11-30"], "closed_weekdays": [{"date": "2026-11-16", "reason": "closed for the trading-system migration"}]}

## get_calendar {"exchange": "WSX", "start_date": "2026-11-13", "end_date": "2026-11-30"}

{"exchange": "WSX", "name": "Westbay Exchange", "start_date": "2026-11-13", "end_date": "2026-11-30", "trading_days": ["2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20", "2026-11-23", "2026-11-24", "2026-11-25", "2026-11-27", "2026-11-30"], "closed_weekdays": [{"date": "2026-11-26", "reason": "Thanksgiving Day"}]}

## get_close {"symbol": "LQVB", "date": "2026-11-13"}

{"symbol": "LQVB", "date": "2026-11-13", "close": 152.35, "currency": "SEK"}

## get_close {"symbol": "EKVN", "date": "2026-11-13"}

{"symbol": "EKVN", "date": "2026-11-13", "close": 246.4, "currency": "SEK"}

## get_close {"symbol": "KZNP", "date": "2026-11-13"}

{"symbol": "KZNP", "date": "2026-11-13", "close": 3615, "currency": "JPY"}

## get_close {"symbol": "VXMR", "date": "2026-11-13"}

{"symbol": "VXMR", "date": "2026-11-13", "close": 87.42, "currency": "USD"}

## get_close {"symbol": "KAFO", "date": "2026-11-13"}

{"symbol": "KAFO", "date": "2026-11-13", "close": 41.36, "currency": "EUR"}

## get_close {"symbol": "BKQM", "date": "2026-11-13"}

{"symbol": "BKQM", "date": "2026-11-13", "close": 318.46, "currency": "SEK"}

## get_close {"symbol": "PLHA", "date": "2026-11-13"}

{"symbol": "PLHA", "date": "2026-11-13", "close": 63.18, "currency": "USD"}

## get_close {"symbol": "RTSY", "date": "2026-11-13"}

{"symbol": "RTSY", "date": "2026-11-13", "close": 58.74, "currency": "EUR"}

## get_fx_fixing {"currency": "USD", "date": "2026-11-13"}

{"currency": "USD", "date": "2026-11-13", "per_eur": 1.1572, "meaning": "1 EUR = 1.1572 USD"}

## get_fx_fixing {"currency": "SEK", "date": "2026-11-13"}

{"currency": "SEK", "date": "2026-11-13", "per_eur": 11.0385, "meaning": "1 EUR = 11.0385 SEK"}

## get_fx_fixing {"currency": "JPY", "date": "2026-11-13"}

{"currency": "JPY", "date": "2026-11-13", "per_eur": 171.42, "meaning": "1 EUR = 171.42 JPY"}

## get_corporate_actions {"symbol": "LQVB"}

{"symbol": "LQVB", "actions": []}

## get_corporate_actions {"symbol": "EKVN"}

{"symbol": "EKVN", "actions": [{"type": "cash dividend", "announced": "2026-08-14", "ex_date": "2026-09-10", "terms": "SEK 2.40 a share, paid on 2026-09-15"}, {"type": "share split", "announced": "2026-11-11", "ex_date": "2026-11-17", "ratio": 4, "terms": "4 new shares for each share held (a 4-for-1 split); from the ex-date the shares trade, and are quoted, as new shares"}]}

## get_corporate_actions {"symbol": "KZNP"}

{"symbol": "KZNP", "actions": [{"type": "cash dividend", "announced": "2026-09-14", "ex_date": "2026-09-29", "terms": "JPY 36 a share, paid on 2026-12-04"}]}

## get_corporate_actions {"symbol": "VXMR"}

{"symbol": "VXMR", "actions": []}

## get_corporate_actions {"symbol": "KAFO"}

{"symbol": "KAFO", "actions": [{"type": "cash dividend", "announced": "2026-09-02", "ex_date": "2026-10-01", "terms": "EUR 0.55 a share, paid on 2026-10-05"}]}

## get_corporate_actions {"symbol": "BKQM"}

{"symbol": "BKQM", "actions": []}

## get_corporate_actions {"symbol": "PLHA"}

{"symbol": "PLHA", "actions": []}

## get_corporate_actions {"symbol": "RTSY"}

{"symbol": "RTSY", "actions": []}

## check_limits {"fund": "NRDF", "symbol": "LQVB", "side": "buy", "quantity": 20200, "limit_price": 152.95, "currency": "SEK"}

{"fund": "NRDF", "book": "start of day, 2026-11-13", "order": {"fund": "NRDF", "symbol": "LQVB", "side": "buy", "quantity": 20200, "limit_price": 152.95, "currency": "SEK"}, "result": "pass", "checks": [{"limit": "issuer concentration", "rule": "at most 5.00% of the fund's NAV in one issuer, after the order", "figure": "0.29% of NAV in Lindqvist Bearings AB after the order (start-of-day holding 0.17%)", "result": "pass"}]}

## check_limits {"fund": "NRDF", "symbol": "EKVN", "side": "buy", "quantity": 37000, "limit_price": 62.3, "currency": "SEK"}

{"fund": "NRDF", "book": "start of day, 2026-11-13", "order": {"fund": "NRDF", "symbol": "EKVN", "side": "buy", "quantity": 37000, "limit_price": 62.3, "currency": "SEK"}, "result": "pass", "checks": [{"limit": "issuer concentration", "rule": "at most 5.00% of the fund's NAV in one issuer, after the order", "figure": "0.09% of NAV in Ekvarn Telecom AB after the order (start-of-day holding 0.00%)", "result": "pass"}]}

## check_limits {"fund": "GLBF", "symbol": "KZNP", "side": "buy", "quantity": 12000, "limit_price": 3605, "currency": "JPY"}

{"fund": "GLBF", "book": "start of day, 2026-11-13", "order": {"fund": "GLBF", "symbol": "KZNP", "side": "buy", "quantity": 12000, "limit_price": 3605, "currency": "JPY"}, "result": "pass", "checks": [{"limit": "issuer concentration", "rule": "at most 5.00% of the fund's NAV in one issuer, after the order", "figure": "0.34% of NAV in Kazenami Precision Co after the order (start-of-day holding 0.28%)", "result": "pass"}]}

## check_limits {"fund": "GLBF", "symbol": "VXMR", "side": "buy", "quantity": 60000, "limit_price": 87.85, "currency": "USD"}

{"fund": "GLBF", "book": "start of day, 2026-11-13", "order": {"fund": "GLBF", "symbol": "VXMR", "side": "buy", "quantity": 60000, "limit_price": 87.85, "currency": "USD"}, "result": "fail", "checks": [{"limit": "issuer concentration", "rule": "at most 5.00% of the fund's NAV in one issuer, after the order", "figure": "5.65% of NAV in Vexmoor Logistics Inc after the order (start-of-day holding 4.45%)", "result": "fail"}]}

## check_limits {"fund": "NRDF", "symbol": "KAFO", "side": "sell", "quantity": 14230, "limit_price": 41.0, "currency": "EUR"}

{"fund": "NRDF", "book": "start of day, 2026-11-13", "order": {"fund": "NRDF", "symbol": "KAFO", "side": "sell", "quantity": 14230, "limit_price": 41.0, "currency": "EUR"}, "result": "pass", "checks": [{"limit": "sale within the holding", "rule": "a sale may not exceed the fund's start-of-day holding of the listing", "figure": "14,230 shares to sell; 42,705 held at the start of the day", "result": "pass"}]}

## check_limits {"fund": "NRDF", "symbol": "BKQM", "side": "buy", "quantity": 8100, "limit_price": 319.4, "currency": "SEK"}

{"fund": "NRDF", "book": "start of day, 2026-11-13", "order": {"fund": "NRDF", "symbol": "BKQM", "side": "buy", "quantity": 8100, "limit_price": 319.4, "currency": "SEK"}, "result": "pass", "checks": [{"limit": "issuer concentration", "rule": "at most 5.00% of the fund's NAV in one issuer, after the order", "figure": "0.22% of NAV in Brekke Marine AB after the order (start-of-day holding 0.12%)", "result": "pass"}]}

## check_limits {"fund": "GLBF", "symbol": "PLHA", "side": "buy", "quantity": 22780, "limit_price": 63.49, "currency": "USD"}

{"fund": "GLBF", "book": "start of day, 2026-11-13", "order": {"fund": "GLBF", "symbol": "PLHA", "side": "buy", "quantity": 22780, "limit_price": 63.49, "currency": "USD"}, "result": "pass", "checks": [{"limit": "issuer concentration", "rule": "at most 5.00% of the fund's NAV in one issuer, after the order", "figure": "0.62% of NAV in Pellham Analytics Inc after the order (start-of-day holding 0.29%)", "result": "pass"}]}

## check_limits {"fund": "GLBF", "symbol": "RTSY", "side": "buy", "quantity": 13175, "limit_price": 58.96, "currency": "EUR"}

{"fund": "GLBF", "book": "start of day, 2026-11-13", "order": {"fund": "GLBF", "symbol": "RTSY", "side": "buy", "quantity": 13175, "limit_price": 58.96, "currency": "EUR"}, "result": "pass", "checks": [{"limit": "issuer concentration", "rule": "at most 5.00% of the fund's NAV in one issuer, after the order", "figure": "0.20% of NAV in Rautio Systems Oyj after the order (start-of-day holding 0.00%)", "result": "pass"}]}
