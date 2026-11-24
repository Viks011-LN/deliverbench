"""The desk's tools around the backtest (docs/tools.md):

  python -m bt.tools.compare A.json B.json        what differs between two reports
  python -m bt.tools.prices_info PRICES.csv       what a price file holds, name by name
  python -m bt.tools.sweep --prices P --config C --set KEY=V1,V2,...
                                                  one config over several values of one setting
  python -m bt.tools.migrate OLD.json             a bt 3.x config in today's layout

None of them changes what `python -m bt` does.
"""
