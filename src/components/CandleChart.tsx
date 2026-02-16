"use client";

type Candle = {
  baseDate: string;
  baseTime: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: string | number;
};

type Props = {
  candles: Candle[];
  symbol: string;
};

export function CandleChart({ candles, symbol }: Props) {
  const width = 900;
  const height = 320;
  const chartTop = 12;
  const chartBottom = 240;
  const volumeTop = 255;
  const volumeBottom = 310;

  if (candles.length === 0) {
    return <div className="card">No candle data yet.</div>;
  }

  const highs = candles.map((c) => c.high);
  const lows = candles.map((c) => c.low);
  const volumes = candles.map((c) => Number(c.volume));
  const minPrice = Math.min(...lows);
  const maxPrice = Math.max(...highs);
  const maxVolume = Math.max(...volumes, 1);
  const xStep = width / Math.max(candles.length, 1);
  const bodyWidth = Math.max(2, xStep * 0.6);

  const priceY = (price: number) => {
    if (maxPrice === minPrice) return (chartTop + chartBottom) / 2;
    return chartBottom - ((price - minPrice) / (maxPrice - minPrice)) * (chartBottom - chartTop);
  };

  const volumeY = (vol: number) =>
    volumeBottom - (vol / maxVolume) * (volumeBottom - volumeTop);

  return (
    <div className="card">
      <div className="chartHeader">
        <h3>{symbol} Candles</h3>
        <span>{candles.length} bars</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="chartSvg">
        <line x1="0" y1={chartBottom} x2={width} y2={chartBottom} className="axis" />
        <line x1="0" y1={volumeTop - 2} x2={width} y2={volumeTop - 2} className="axis" />
        {candles.map((candle, index) => {
          const x = index * xStep + xStep / 2;
          const openY = priceY(candle.open);
          const closeY = priceY(candle.close);
          const highY = priceY(candle.high);
          const lowY = priceY(candle.low);
          const rise = candle.close >= candle.open;
          const color = rise ? "#16a34a" : "#dc2626";
          const bodyTop = Math.min(openY, closeY);
          const bodyHeight = Math.max(1, Math.abs(openY - closeY));
          const volY = volumeY(Number(candle.volume));

          return (
            <g key={`${candle.baseDate}-${candle.baseTime}-${index}`}>
              <line x1={x} y1={highY} x2={x} y2={lowY} stroke={color} strokeWidth="1.2" />
              <rect
                x={x - bodyWidth / 2}
                y={bodyTop}
                width={bodyWidth}
                height={bodyHeight}
                fill={color}
                opacity="0.9"
              />
              <rect
                x={x - bodyWidth / 2}
                y={volY}
                width={bodyWidth}
                height={Math.max(1, volumeBottom - volY)}
                fill="#60a5fa"
                opacity="0.45"
              />
            </g>
          );
        })}
      </svg>
    </div>
  );
}
