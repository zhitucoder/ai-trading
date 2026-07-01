from fastapi import APIRouter, Query
from ..database import query
from datetime import datetime, timedelta

router = APIRouter()


def find_local_extrema(prices, min_distance=3):
    peaks = []
    troughs = []
    n = len(prices)
    for i in range(1, n - 1):
        left = max(0, i - min_distance)
        right = min(n - 1, i + min_distance)
        if prices[i] == max(prices[left:right + 1]) and prices[i] != prices[i - 1]:
            if not peaks or (i - peaks[-1][0]) >= min_distance:
                peaks.append((i, prices[i]))
        if prices[i] == min(prices[left:right + 1]) and prices[i] != prices[i - 1]:
            if not troughs or (i - troughs[-1][0]) >= min_distance:
                troughs.append((i, prices[i]))
    return peaks, troughs


def detect_vcp(kline_rows, stock_code, stock_name, min_pct=3, lookback_days=150):
    if len(kline_rows) < 60:
        return None

    close = [float(r['close_price']) for r in kline_rows]
    dates = [r['trade_date'] for r in kline_rows]

    n = len(close)
    ma50 = sum(close[-50:]) / 50
    ma150 = sum(close[-150:]) / 150 if n >= 150 else ma50 * 0.9

    latest_price = close[-1]
    latest_date = dates[-1]

    if latest_price < ma50 or latest_price < ma150:
        return None

    recent_half = max(n - lookback_days, 0)
    peaks, troughs = find_local_extrema(close[recent_half:])
    peaks = [(i + recent_half, p) for i, p in peaks]
    troughs = [(i + recent_half, p) for i, p in troughs]

    relevant_peaks = [(i, p) for i, p in peaks if i >= n - lookback_days and i >= n - 80]
    if not relevant_peaks:
        return None

    pivot_idx, pivot_price = max(relevant_peaks, key=lambda x: x[1])

    after_pivot = close[pivot_idx:]
    if len(after_pivot) < 10:
        return None

    trough_after = []
    for i, tp in troughs:
        if i > pivot_idx:
            trough_after.append((i, tp))

    if not trough_after:
        return None

    t1_idx, t1_val = trough_after[0]
    t1_decline = (pivot_price - t1_val) / pivot_price * 100
    if t1_decline < min_pct or t1_decline > 35:
        return None

    contractions = [{
        'label': 'T1',
        'peak_price': round(pivot_price, 2),
        'trough_price': round(t1_val, 2),
        'decline_pct': round(t1_decline, 2),
        'is_complete': True,
    }]

    prev_peak = pivot_price
    prev_trough = t1_val
    last_idx = t1_idx

    for t_num in range(2, 7):
        sub = close[last_idx:]
        sp, st = find_local_extrema(sub, min_distance=2)
        if not sp:
            break

        next_peak = None
        for pi, pp in sp:
            actual_pi = last_idx + pi
            if pp > prev_trough * 1.02 and actual_pi < n - 3:
                next_peak = (actual_pi, pp)
                break

        if next_peak is None:
            break

        np_idx, np_val = next_peak
        bounce = (np_val - prev_trough) / prev_trough * 100

        sub2 = close[np_idx:]
        if len(sub2) < 5:
            break
        min_in_sub2 = min(sub2)
        if min_in_sub2 >= np_val:
            break

        min_rel_idx = sub2.index(min_in_sub2)
        nt_idx = np_idx + min_rel_idx
        nt_val = min_in_sub2
        t_decline = (np_val - nt_val) / np_val * 100

        if nt_val <= 0 or np_val <= 0:
            break

        last_con = contractions[-1]
        if t_decline >= last_con['decline_pct']:
            break
        if t_decline < 1 or t_decline > 30:
            break

        tightness = (max(close[np_idx:nt_idx + 1]) - min(close[np_idx:nt_idx + 1])) / np_val * 100 if nt_idx > np_idx else 0
        is_last = nt_idx >= n - 5

        contractions.append({
            'label': f'T{t_num}',
            'peak_price': round(np_val, 2),
            'trough_price': round(nt_val, 2),
            'decline_pct': round(t_decline, 2),
            'tightness_pct': round(tightness, 2),
            'is_complete': is_last,
        })

        prev_peak = np_val
        prev_trough = nt_val
        last_idx = nt_idx

    if len(contractions) < 2:
        return None

    avg_volume_50 = sum(r['volume'] for r in kline_rows[-50:]) / 50
    avg_volume_10 = sum(r['volume'] for r in kline_rows[-10:]) / 50 if avg_volume_50 else 1

    recent_20 = close[-20:]
    tightness = (max(recent_20) - min(recent_20)) / (sum(recent_20) / len(recent_20) + 0.01) * 100

    vol_ratio = avg_volume_10 / avg_volume_50 if avg_volume_50 > 0 else 1
    volume_dry = vol_ratio < 0.8
    volume_surge = vol_ratio > 1.5

    distance_from_pivot = (latest_price - pivot_price) / pivot_price * 100
    break_out = distance_from_pivot > 2 and volume_surge and latest_price > pivot_price
    near_pivot = abs(distance_from_pivot) < 3
    above_pivot = latest_price > pivot_price
    distance_from_last_trough = (latest_price - prev_trough) / prev_trough * 100 if prev_trough else 0

    return {
        'stock_code': stock_code,
        'stock_name': stock_name,
        'latest_price': round(latest_price, 2),
        'latest_date': str(latest_date)[:10],
        'pivot_price': round(pivot_price, 2),
        'contractions': contractions,
        'contraction_count': len(contractions),
        'current_tightness': round(tightness, 2),
        'volume_ratio': round(vol_ratio, 2),
        'volume_dry_up': volume_dry,
        'volume_surge': volume_surge,
        'distance_from_pivot_pct': round(distance_from_pivot, 2),
        'distance_from_last_trough_pct': round(distance_from_last_trough, 2),
        'near_pivot': near_pivot,
        'breakout_signal': break_out,
        'above_pivot': above_pivot,
        'ma50_ma150': f'{round(ma50, 2)} / {round(ma150, 2)}',
    }


@router.get('/scan')
def scan_vcp(
    min_contractions: int = Query(2, ge=1, le=6),
    max_contractions: int = Query(6, ge=2, le=10),
    min_pct: float = Query(3, ge=1, le=20),
    lookback_days: int = Query(150, ge=60, le=365),
    max_stocks: int = Query(50, ge=10, le=200),
):
    tdate_row = query("SELECT MAX(trade_date) AS d FROM daily_kline")
    if not tdate_row:
        return {'rows': [], 'total': 0}
    tdate = tdate_row[0]['d']
    lookback_start = tdate - timedelta(days=lookback_days + 30)

    code_rows = query("""
        SELECT DISTINCT d.stock_code
        FROM daily_kline d
        JOIN stocks s ON s.stock_code = d.stock_code
        WHERE d.trade_date = %s
          AND d.close_price > 0
          AND d.close_price IS NOT NULL
    """, [tdate])

    all_codes = [r['stock_code'] for r in code_rows]
    results = []

    for sc in all_codes[:500]:
        kline = query("""
            SELECT trade_date, close_price, volume
            FROM daily_kline
            WHERE stock_code = %s
              AND trade_date >= %s
              AND trade_date <= %s
            ORDER BY trade_date
        """, [sc, lookback_start, tdate])

        if len(kline) < 60:
            continue

        name_row = query("SELECT stock_name FROM stocks WHERE stock_code = %s", [sc])
        sname = name_row[0]['stock_name'] if name_row else sc

        result = detect_vcp(kline, sc, sname, min_pct=min_pct, lookback_days=lookback_days)
        if result and min_contractions <= result['contraction_count'] <= max_contractions:
            results.append(result)

        if len(results) >= max_stocks:
            break

    results.sort(key=lambda r: (-r['contraction_count'], r['current_tightness']))
    return {'rows': results, 'total': len(results)}
