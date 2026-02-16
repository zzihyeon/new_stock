type BacktestInputCandle = {
  baseDate: string;
  close: number;
};

export type BacktestResult = {
  initialCapital: number;
  finalCapital: number;
  totalReturnPct: number;
  maxDrawdownPct: number;
  trades: number;
  equityCurve: Array<{ date: string; equity: number }>;
};

function calcSma(values: number[], period: number): Array<number | null> {
  const sma: Array<number | null> = Array(values.length).fill(null);
  let sum = 0;
  for (let i = 0; i < values.length; i += 1) {
    sum += values[i];
    if (i >= period) {
      sum -= values[i - period];
    }
    if (i >= period - 1) {
      sma[i] = sum / period;
    }
  }
  return sma;
}

export function runSimpleSmaBacktest(
  candles: BacktestInputCandle[],
  initialCapital: number,
  shortPeriod = 5,
  longPeriod = 20,
): BacktestResult {
  const closes = candles.map((c) => c.close);
  const short = calcSma(closes, shortPeriod);
  const long = calcSma(closes, longPeriod);

  let cash = initialCapital;
  let shares = 0;
  let trades = 0;
  let maxEquity = initialCapital;
  let maxDrawdown = 0;
  const equityCurve: Array<{ date: string; equity: number }> = [];

  for (let i = 0; i < candles.length; i += 1) {
    const price = candles[i].close;
    const shortNow = short[i];
    const longNow = long[i];
    const shortPrev = i > 0 ? short[i - 1] : null;
    const longPrev = i > 0 ? long[i - 1] : null;

    if (
      shortNow !== null &&
      longNow !== null &&
      shortPrev !== null &&
      longPrev !== null
    ) {
      const goldenCross = shortPrev <= longPrev && shortNow > longNow;
      const deadCross = shortPrev >= longPrev && shortNow < longNow;

      if (goldenCross && shares === 0 && price > 0) {
        shares = cash / price;
        cash = 0;
        trades += 1;
      } else if (deadCross && shares > 0) {
        cash = shares * price;
        shares = 0;
        trades += 1;
      }
    }

    const equity = cash + shares * price;
    maxEquity = Math.max(maxEquity, equity);
    const drawdown = maxEquity > 0 ? ((maxEquity - equity) / maxEquity) * 100 : 0;
    maxDrawdown = Math.max(maxDrawdown, drawdown);
    equityCurve.push({ date: candles[i].baseDate, equity });
  }

  const finalEquity =
    equityCurve.length > 0 ? equityCurve[equityCurve.length - 1].equity : initialCapital;

  return {
    initialCapital,
    finalCapital: finalEquity,
    totalReturnPct: ((finalEquity - initialCapital) / initialCapital) * 100,
    maxDrawdownPct: maxDrawdown,
    trades,
    equityCurve,
  };
}
