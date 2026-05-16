import yfinance as yf
from typing import Dict, Tuple
import json
from datetime import datetime

# Global portfolio storage
portfolio = {}
current_prices = {}
transactions: list = []


def _load_transactions(path: str = "transactions.json") -> list:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def _save_transactions(txns: list, path: str = "transactions.json") -> None:
    with open(path, "w") as f:
        json.dump(txns, f, indent=2, sort_keys=True)


def get_rebalance_recommendations() -> Dict[str, Dict]:
    """Compute recommended trades to rebalance portfolio to targets.

    Returns mapping ticker -> {action, shares_change, dollar_change, price}
    """
    if not portfolio or not current_prices:
        raise RuntimeError("portfolio or prices not set")

    # compute holdings values and total value
    holdings_value = {}
    total_value = 0.0
    for t, (qty, _) in portfolio.items():
        price = float(current_prices.get(t, 0) or 0)
        val = qty * price
        holdings_value[t] = val
        total_value += val

    recommendations: Dict[str, Dict] = {}
    for t, (qty, target_alloc) in portfolio.items():
        price = float(current_prices.get(t, 0) or 0)
        target_value = target_alloc * total_value
        current_value = holdings_value.get(t, 0)
        dollar_change = target_value - current_value
        shares_change = (dollar_change / price) if price else 0.0
        action = "none"
        if abs(shares_change) >= 1e-12:
            action = "BUY" if shares_change > 0 else "SELL"
        recommendations[t] = {
            "action": action,
            "shares_change": shares_change,
            "dollar_change": dollar_change,
            "price": price,
        }

    return recommendations


def execute_rebalance(record: bool = True, tx_path: str = "transactions.json") -> list:
    """Execute recommended trades and optionally record transactions to disk.

    Returns the list of transaction records appended.
    """
    recs = get_rebalance_recommendations()
    txns = _load_transactions(tx_path)

    for t, r in recs.items():
        if r["action"] == "none":
            continue
        shares = r["shares_change"]
        # update portfolio quantity
        qty, target_alloc = portfolio[t]
        new_qty = qty + shares
        portfolio[t] = (new_qty, target_alloc)

        txn = {
            "date": datetime.utcnow().isoformat() + "Z",
            "ticker": t,
            "action": r["action"],
            "shares": round(abs(shares), 4),
            "dollar_amount": round(abs(r["dollar_change"]), 2),
            "price": r["price"],
        }
        txns.append(txn)

    if record:
        _save_transactions(txns, tx_path)

    return txns


def execute_transaction(ticker: str, action: str, shares: float, price: float | None = None, record: bool = True, tx_path: str = "transactions.json") -> dict:
    """Apply an arbitrary transaction to the portfolio and optionally record it.

    - ticker: ticker symbol (case-insensitive)
    - action: 'buy' or 'sell'
    - shares: positive number of shares to buy/sell
    - price: optional execution price; if None, will use current_prices[ticker]
    Returns the transaction record dict.
    """
    t = ticker.upper()
    if t not in portfolio:
        raise KeyError(f"ticker {t} not in portfolio")

    act = action.strip().lower()
    if act not in ("buy", "sell"):
        raise ValueError("action must be 'buy' or 'sell'")

    if shares <= 0:
        raise ValueError("shares must be positive")

    exec_price = price
    if exec_price is None:
        exec_price = current_prices.get(t)
        if exec_price is None:
            raise RuntimeError(f"no price available for {t}; supply a price")

    exec_price = float(exec_price)

    # apply trade to portfolio
    qty, target_alloc = portfolio[t]
    if act == "buy":
        new_qty = qty + shares
    else:
        new_qty = qty - shares
    portfolio[t] = (new_qty, target_alloc)

    dollar_amount = round(shares * exec_price, 2)
    txn = {
        "date": datetime.utcnow().isoformat() + "Z",
        "ticker": t,
        "action": act.upper(),
        "shares": round(shares, 4),
        "dollar_amount": dollar_amount,
        "price": exec_price,
    }

    if record:
        txns = _load_transactions(tx_path)
        txns.append(txn)
        _save_transactions(txns, tx_path)

    return txn


def set_portfolio_weight_change(changes: Dict[str, float], normalize: bool = True) -> Dict[str, Tuple[float, float]]:
    """Change the desired weights (target allocations) for tickers in the portfolio.

    - changes: mapping ticker -> new weight (floats, need not sum to 1)
    - normalize: if True, weights are normalized to sum to 1.

    Only tickers already present in `portfolio` will be updated; others are ignored.
    Returns the updated portfolio dict.
    """
    if not portfolio:
        raise RuntimeError("portfolio not set")

    # require that the user provided weights for all portfolio tickers
    if not changes:
        raise ValueError("no weight changes provided")

    portfolio_tickers = set(portfolio.keys())
    provided_tickers = {k.upper() for k in changes.keys()}
    if portfolio_tickers != provided_tickers:
        missing = portfolio_tickers - provided_tickers
        extra = provided_tickers - portfolio_tickers
        msg_parts = []
        if missing:
            msg_parts.append(f"missing tickers: {', '.join(sorted(missing))}")
        if extra:
            msg_parts.append(f"unknown tickers: {', '.join(sorted(extra))}")
        raise ValueError("must provide weights for all portfolio tickers; " + "; ".join(msg_parts))

    # validate and collect
    new_weights: Dict[str, float] = {k.upper(): float(v) for k, v in changes.items()}

    # require weights sum to 1
    total = sum(new_weights.values())
    tol = 1e-9
    if abs(total - 1.0) > tol:
        raise ValueError(f"provided weights must sum to 1. Got sum={total}")

    # apply changes to portfolio entries; leave quantities unchanged
    for t, (qty, _) in portfolio.items():
        portfolio[t] = (qty, new_weights[t])

    return portfolio



def set_portfolio(holdings: Dict[str, Tuple[float, float]]) -> None:
    """
    Set the current portfolio with target allocations.
    
    Args:
        holdings: Dictionary with format {
            'TICKER': (quantity, target_allocation_percent)
        }
        Example: {'AAPL': (10, 0.40), 'MSFT': (5, 0.30), 'CASH': (1000, 0.30)}
    """
    # validate that target weights sum to 1
    total = 0.0
    for t, (_, target) in holdings.items():
        try:
            total += float(target)
        except Exception:
            raise ValueError(f"invalid target weight for {t}")
    tol = 1e-9
    if abs(total - 1.0) > tol:
        raise ValueError(f"target allocations must sum to 1. Got sum={total}")

    # validate tickers with yfinance before accepting
    invalid = validate_tickers(list(holdings.keys()))
    if invalid:
        raise ValueError(f"unrecognized tickers: {', '.join(invalid)}")

    global portfolio
    portfolio = holdings
    print(f"Portfolio set with {len(holdings)} assets")
    print(f"Portfolio: {holdings}")


def get_current_prices(tickers: list) -> Dict[str, float]:
    """
    Fetch current prices for given tickers using yFinance.
    
    Args:
        tickers: List of ticker symbols (e.g., ['AAPL', 'MSFT'])
    
    Returns:
        Dictionary with format {'TICKER': current_price}
    """
    global current_prices
    
    try:
        # Remove 'CASH' if present (it doesn't have a price)
        tickers_to_fetch = [t for t in tickers if t.upper() != 'CASH']
        
        if not tickers_to_fetch:
            current_prices = {}
            return {}
        
        # Fetch prices
        data = yf.download(tickers_to_fetch, period='1d', progress=False)
        
        # Helper function to extract float value
        def get_float_value(val):
            if hasattr(val, 'item'):  # numpy/pandas scalar
                return float(val.item())
            return float(val)
        
        # Handle single ticker vs multiple
        if len(tickers_to_fetch) == 1:
            price = get_float_value(data['Close'].iloc[-1])
            current_prices = {tickers_to_fetch[0]: price}
        else:
            prices_series = data['Close'].iloc[-1]
            current_prices = {k: get_float_value(v) for k, v in prices_series.items()}
        
        # Add cash with price of 1
        if 'CASH' in tickers:
            current_prices['CASH'] = 1.0
        
        print(f"Current prices fetched: {current_prices}")
        return current_prices
        
    except Exception as e:
        print(f"Error fetching prices: {e}")
        return {}


def validate_tickers(tickers: list) -> list:
    """Return a list of tickers that yfinance does NOT recognize.

    For each ticker we try a short download; if no usable price is returned we
    consider it invalid.
    """
    invalid = []
    for t in tickers:
        tt = str(t).upper()
        try:
            data = yf.download(tt, period="5d", progress=False)
            if data is None or data.empty:
                invalid.append(tt)
                continue
            # prefer Adj Close or Close
            if isinstance(data, dict):
                invalid.append(tt)
                continue
            # last row may be NaN for some tickers
            last = None
            for col in ("Adj Close", "Close"):
                if col in data.columns:
                    s = data[col].dropna()
                    if not s.empty:
                        last = s.iloc[-1]
                        break
            if last is None:
                # try if single-column dataframe
                try:
                    lastrow = data.dropna(how="all").iloc[-1]
                    # if lastrow is a Series with values
                    if lastrow is None or (hasattr(lastrow, 'isnull') and lastrow.isnull().all()):
                        invalid.append(tt)
                        continue
                except Exception:
                    invalid.append(tt)
                    continue
        except Exception:
            invalid.append(tt)
    return invalid


def get_portfolio() -> dict:
    """Return the current portfolio as a serializable dict {ticker: [quantity, target]}.

    GUI uses this to get the tickers to fetch prices for.
    """
    return {k: [v[0], v[1]] for k, v in portfolio.items()}


def check_rebalance(threshold: float = 5.0) -> Dict:
    """
    Check if portfolio needs rebalancing based on threshold.
    
    Args:
        threshold: Rebalancing threshold in percentage (default 5%)
    
    Returns:
        Dictionary with format {
            'needs_rebalance': bool,
            'current_allocations': {ticker: current_percent},
            'target_allocations': {ticker: target_percent},
            'differences': {ticker: difference_percent},
            'assets_to_adjust': list of tickers exceeding threshold
        }
    """
    if not portfolio or not current_prices:
        print("Error: Portfolio or prices not set")
        return {'needs_rebalance': False}
    
    # Calculate current portfolio value
    portfolio_value = 0
    holdings_value = {}
    
    for ticker, (quantity, target_alloc) in portfolio.items():
        price_val = current_prices.get(ticker, 0)
        price = float(price_val) if price_val != 0 else 0
        value = quantity * price
        holdings_value[ticker] = value
        portfolio_value += value
    
    # Calculate current vs target allocations
    current_allocations = {}
    target_allocations = {}
    differences = {}
    assets_to_adjust = []
    
    for ticker, (_, target_alloc) in portfolio.items():
        current_alloc = (holdings_value.get(ticker, 0) / portfolio_value * 100) if portfolio_value > 0 else 0
        current_allocations[ticker] = round(current_alloc, 2)
        target_allocations[ticker] = target_alloc * 100
        diff = abs(current_alloc - (target_alloc * 100))
        differences[ticker] = round(diff, 2)
        
        if diff > threshold:
            assets_to_adjust.append(ticker)
    
    needs_rebalance = len(assets_to_adjust) > 0
    
    result = {
        'needs_rebalance': needs_rebalance,
        'portfolio_value': round(portfolio_value, 2),
        'current_allocations': current_allocations,
        'target_allocations': target_allocations,
        'differences': differences,
        'assets_to_adjust': assets_to_adjust,
        'threshold': threshold
    }
    
    print(f"\n--- Rebalance Check ---")
    print(f"Portfolio Value: ${result['portfolio_value']}")
    print(f"Needs Rebalance: {needs_rebalance}")
    print(f"Current vs Target Allocations:")
    for ticker in portfolio:
        print(f"  {ticker}: {current_allocations[ticker]}% (target: {target_allocations[ticker]}%, diff: {differences[ticker]}%)")
    # Recommended trades block: compute per-ticker buy/sell recommendation to reach target
    print(f"\nRecommended Trades:")
    any_trade = False
    for ticker, (quantity, target_alloc) in portfolio.items():
        price_val = current_prices.get(ticker, 0)
        try:
            price = float(price_val) if price_val is not None else 0.0
        except Exception:
            price = 0.0

        # compute dollar and share change needed to reach target
        current_value = holdings_value.get(ticker, 0)
        target_value = (target_alloc * result['portfolio_value'])
        dollar_change = target_value - current_value
        # avoid division by zero
        shares_change = (dollar_change / price) if price else 0.0

        if abs(shares_change) < 1e-12:
            continue

        any_trade = True
        if shares_change > 0:
            sign = '+'
            action = 'BUY'
        else:
            sign = '-'
            action = 'SELL'

        # print with arrow prefix, + for buys and - for sells
        print(f"  → {ticker}: {action} {sign}${abs(dollar_change):.2f}, {sign}{abs(shares_change):.4f} shares")

    if needs_rebalance:
        print(f"Assets exceeding {threshold}% threshold: {assets_to_adjust}")
    
    return result


def main():
    """Interactive CLI for portfolio rebalancer."""
    print("=" * 50)
    print("Portfolio Rebalancer CLI")
    print("=" * 50)

    threshold = 5.0

    while True:
        print("\nOptions:")
        print("1. Set portfolio")
        print("2. Get current prices")
        print("3. Check rebalance (5% threshold)")
        print("4. Set custom threshold")
        print("5. View portfolio")
        print("6. Exit")
        print("7. Execute rebalance and record transactions")
        print("8. Record an arbitrary transaction (buy/sell)")
        print("9. Set portfolio weight change")

        choice = input("\nEnter choice (1-9): ").strip()

        if choice == '1':
            print("\nSet portfolio holdings (format: ticker quantity target_percent)")
            print("Example: SPY 20 0.50")
            holdings = {}
            while True:
                line = input("Enter holding (or 'done'): ").strip()
                if line.lower() == 'done':
                    break
                try:
                    parts = line.split()
                    if len(parts) != 3:
                        print("Invalid format. Use: ticker quantity target_percent")
                        continue
                    ticker = parts[0].upper()
                    quantity = float(parts[1])
                    target = float(parts[2])
                    holdings[ticker] = (quantity, target)
                except ValueError:
                    print("Invalid input. Please use: ticker quantity target_percent")

            if holdings:
                try:
                    invalid = validate_tickers(list(holdings.keys()))
                    if invalid:
                        print(f"Error: unrecognized tickers: {', '.join(invalid)}")
                    else:
                        set_portfolio(holdings)
                except Exception as exc:
                    print(f"Error setting portfolio: {exc}")
            else:
                print("No holdings entered.")

        elif choice == '2':
            if not portfolio:
                print("Error: Portfolio not set. Use option 1 first.")
                continue
            tickers = list(portfolio.keys())
            get_current_prices(tickers)

        elif choice == '3':
            if not portfolio or not current_prices:
                print("Error: Portfolio and prices not set.")
                continue
            check_rebalance(threshold=threshold)

        elif choice == '4':
            try:
                new_threshold = float(input("Enter new threshold (%): "))
            except ValueError:
                print("Invalid input. Please enter a number.")
                continue

            # enforce 0 <= threshold < 100
            if not (0 <= new_threshold < 100):
                print("Threshold must be >= 0 and less than 100%.")
                continue

            threshold = new_threshold
            print(f"Threshold set to {threshold}%")

        elif choice == '5':
            if not portfolio:
                print("Portfolio not set.")
            else:
                print("\nCurrent Portfolio:")
                for ticker, (qty, target) in portfolio.items():
                    print(f"  {ticker}: {qty} shares (target: {target*100}%)")
                if current_prices:
                    print("\nCurrent Prices:")
                    for ticker, price in current_prices.items():
                        price_val = float(price)
                        print(f"  {ticker}: ${price_val:.2f}")

        elif choice == '6':
            print("Goodbye!")
            break

        elif choice == '7':
            # execute the rebalance and record transactions
            if not portfolio or not current_prices:
                print("Error: Portfolio and prices must be set before executing rebalance.")
                continue
            txns = execute_rebalance(record=True)
            if txns:
                print("Transactions recorded:")
                for tx in txns[-10:]:  # show last up to 10 transactions
                    print(f"  {tx['date']} - {tx['ticker']}: {tx['action']} ${tx['dollar_amount']:.2f} ({tx['shares']} shares) @ {tx['price']}")
            else:
                print("No transactions were necessary.")

        elif choice == '8':
            if not portfolio:
                print("Error: Portfolio not set. Use option 1 first.")
                continue
            try:
                t = input("Ticker: ").strip().upper()
                a = input("Action (buy/sell): ").strip().lower()
                s = float(input("Shares: ").strip())
                p_in = input("Price (leave blank to use current price): ").strip()
                p = float(p_in) if p_in else None
                txn = execute_transaction(ticker=t, action=a, shares=s, price=p, record=True)
                print(f"Recorded: {txn['date']} - {txn['ticker']} {txn['action']} ${txn['dollar_amount']:.2f} ({txn['shares']} shares) @ {txn['price']}")
            except Exception as exc:
                print(f"Error recording transaction: {exc}")

        elif choice == '9':
            if not portfolio:
                print("Portfolio not set. Use option 1 first.")
                continue
            print("Enter ticker and new weight (one per line), e.g. 'SPY 0.6'. Type 'done' when finished.")
            changes: Dict[str, float] = {}
            while True:
                line = input("Ticker weight (or 'done'): ").strip()
                if line.lower() == 'done':
                    break
                try:
                    tk, wt = line.split()
                    changes[tk.upper()] = float(wt)
                except Exception:
                    print("Invalid input. Use: TICKER weight")
            try:
                set_portfolio_weight_change(changes)
                print("Portfolio weights updated.")
            except Exception as exc:
                print(f"Error updating weights: {exc}")

        else:
            print("Invalid choice. Please enter 1-9.")


if __name__ == "__main__":
    main()
