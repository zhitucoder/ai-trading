from ..database import query

VOLUME_SURGE_STRATEGIES = {
    'volume_surge_three_stage': {
        'name': '三阶倍量柱+王者倍量柱',
        'description': '2个月内出现3个倍量柱，且最后一个收盘价>前两个，最后一个是王者倍量柱（量缩价升）',
        'params': {
            'lookback_months': {'type': 'int', 'default': 2, 'description': '回溯月数'},
            'volume_ratio_min': {'type': 'float', 'default': 1.5, 'description': '成交量放大倍数下限'},
            'volume_ratio_max': {'type': 'float', 'default': 4.0, 'description': '成交量放大倍数上限'},
            'shrink_days': {'type': 'int', 'default': 3, 'description': '王者倍量柱后缩量天数'},
        },
    },
    'volume_surge_consecutive_king': {
        'name': '连续王者倍量柱',
        'description': '出现王者倍量柱后，3-10天内又出现另一个王者倍量柱',
        'params': {
            'lookback_months': {'type': 'int', 'default': 2, 'description': '回溯月数'},
            'volume_ratio_min': {'type': 'float', 'default': 1.5, 'description': '成交量放大倍数下限'},
            'volume_ratio_max': {'type': 'float', 'default': 4.0, 'description': '成交量放大倍数上限'},
            'shrink_days': {'type': 'int', 'default': 3, 'description': '王者倍量柱后缩量天数'},
            'min_gap_days': {'type': 'int', 'default': 3, 'description': '连续王者倍量柱最小间隔天数'},
            'max_gap_days': {'type': 'int', 'default': 10, 'description': '连续王者倍量柱最大间隔天数'},
        },
    },
}


def detect_volume_surge(stocks_sql_result, lookback_months=2, vol_min=1.5, vol_max=4.0):
    if not stocks_sql_result:
        return []

    stock_codes = [r['stock_code'] for r in stocks_sql_result]
    if not stock_codes:
        return []

    placeholders = ','.join(['%s'] * len(stock_codes))

    sql = f"""
    WITH kline AS (
        SELECT k.stock_code, k.trade_date, k.close_price, k.volume,
               LAG(k.volume) OVER (PARTITION BY k.stock_code ORDER BY k.trade_date) AS prev_volume
        FROM daily_kline k
        WHERE k.stock_code IN ({placeholders})
          AND k.trade_date >= DATE_SUB((SELECT MAX(trade_date) FROM daily_kline), INTERVAL {lookback_months} MONTH)
    )
    SELECT stock_code, trade_date, close_price, volume, prev_volume,
           ROUND(volume / prev_volume, 2) AS vol_ratio
    FROM kline
    WHERE prev_volume IS NOT NULL
      AND prev_volume > 0
      AND volume >= prev_volume * %s
      AND volume <= prev_volume * %s
    ORDER BY stock_code, trade_date
    """
    return query(sql, stock_codes + [vol_min, vol_max])


def detect_three_stage_kings(all_surge_records, shrink_days=3):
    if not all_surge_records:
        return []

    # Group by stock_code
    by_stock = {}
    for r in all_surge_records:
        code = r['stock_code']
        by_stock.setdefault(code, []).append(r)

    results = []
    for code, surges in by_stock.items():
        surges.sort(key=lambda x: x['trade_date'])
        n = len(surges)
        if n < 3:
            continue

        # Check all combinations of 3 surges
        for i in range(n - 2):
            for j in range(i + 1, n - 1):
                for k in range(j + 1, n):
                    s1, s2, s3 = surges[i], surges[j], surges[k]

                    # Condition: s3 close_price > s1 and s2 close_price
                    if s3['close_price'] <= s1['close_price'] or s3['close_price'] <= s2['close_price']:
                        continue

                    # Check king surge: next shrink_days after s3
                    is_king = check_king_surge(code, s3['trade_date'], shrink_days)
                    if is_king:
                        results.append({
                            'stock_code': code,
                            'surge1_date': s1['trade_date'].strftime('%Y-%m-%d') if hasattr(s1['trade_date'], 'strftime') else str(s1['trade_date'])[:10],
                            'surge1_close': float(s1['close_price']),
                            'surge1_ratio': float(s1['vol_ratio']),
                            'surge2_date': s2['trade_date'].strftime('%Y-%m-%d') if hasattr(s2['trade_date'], 'strftime') else str(s2['trade_date'])[:10],
                            'surge2_close': float(s2['close_price']),
                            'surge2_ratio': float(s2['vol_ratio']),
                            'surge3_date': s3['trade_date'].strftime('%Y-%m-%d') if hasattr(s3['trade_date'], 'strftime') else str(s3['trade_date'])[:10],
                            'surge3_close': float(s3['close_price']),
                            'surge3_ratio': float(s3['vol_ratio']),
                            'king_confirmed': True,
                        })
                        break  # Found one valid combination for this stock
                else:
                    continue
                break
            else:
                continue
            break

    # Deduplicate by stock_code (keep first valid)
    seen = set()
    deduped = []
    for r in results:
        if r['stock_code'] not in seen:
            seen.add(r['stock_code'])
            deduped.append(r)

    return deduped


def detect_consecutive_kings(all_surge_records, shrink_days=3, min_gap=3, max_gap=10):
    if not all_surge_records:
        return []

    by_stock = {}
    for r in all_surge_records:
        code = r['stock_code']
        by_stock.setdefault(code, []).append(r)

    results = []
    for code, surges in by_stock.items():
        surges.sort(key=lambda x: x['trade_date'])
        n = len(surges)

        # Find all king surges first
        king_indices = []
        for idx, surge in enumerate(surges):
            if check_king_surge(code, surge['trade_date'], shrink_days):
                king_indices.append(idx)

        if len(king_indices) < 2:
            continue

        # Check for consecutive kings within gap range
        for i in range(len(king_indices)):
            for j in range(i + 1, len(king_indices)):
                idx1, idx2 = king_indices[i], king_indices[j]
                s1, s2 = surges[idx1], surges[idx2]

                # Calculate gap in days
                from datetime import datetime
                if hasattr(s1['trade_date'], 'strftime'):
                    d1 = s1['trade_date']
                else:
                    d1 = datetime.strptime(str(s1['trade_date'])[:10], '%Y-%m-%d')
                if hasattr(s2['trade_date'], 'strftime'):
                    d2 = s2['trade_date']
                else:
                    d2 = datetime.strptime(str(s2['trade_date'])[:10], '%Y-%m-%d')

                gap_days = (d2 - d1).days

                if min_gap <= gap_days <= max_gap:
                    results.append({
                        'stock_code': code,
                        'king1_date': d1.strftime('%Y-%m-%d'),
                        'king1_close': float(s1['close_price']),
                        'king1_ratio': float(s1['vol_ratio']),
                        'king2_date': d2.strftime('%Y-%m-%d'),
                        'king2_close': float(s2['close_price']),
                        'king2_ratio': float(s2['vol_ratio']),
                        'gap_days': gap_days,
                        'consecutive_king_confirmed': True,
                    })
                    break  # Found one valid pair for this stock

    seen = set()
    deduped = []
    for r in results:
        if r['stock_code'] not in seen:
            seen.add(r['stock_code'])
            deduped.append(r)

    return deduped


def check_king_surge(stock_code, surge_date, shrink_days=3):
    sql = """
    SELECT trade_date, close_price, volume
    FROM daily_kline
    WHERE stock_code = %s
      AND trade_date > %s
    ORDER BY trade_date
    LIMIT %s
    """
    future_rows = query(sql, [stock_code, surge_date, shrink_days])

    if len(future_rows) < shrink_days:
        return False

    surge_close = None
    # Get surge close price
    surge_sql = "SELECT close_price FROM daily_kline WHERE stock_code = %s AND trade_date = %s"
    surge_row = query(surge_sql, [stock_code, surge_date])
    if not surge_row:
        return False
    surge_close = float(surge_row[0]['close_price'])

    # Check: avg close_price of next days > surge close_price
    avg_close = sum(float(r['close_price']) for r in future_rows) / len(future_rows)
    if avg_close <= surge_close:
        return False

    # Check: avg volume of next days < surge volume (volume shrinking)
    surge_vol = None
    vol_sql = "SELECT volume FROM daily_kline WHERE stock_code = %s AND trade_date = %s"
    vol_row = query(vol_sql, [stock_code, surge_date])
    if not vol_row:
        return False
    surge_vol = float(vol_row[0]['volume'])

    avg_vol = sum(float(r['volume']) for r in future_rows) / len(future_rows)
    if avg_vol >= surge_vol:
        return False

    return True


def screen_volume_surge(strategy_id='volume_surge_three_stage', lookback_months=2, vol_min=1.5, vol_max=4.0, shrink_days=3, min_gap=3, max_gap=10):
    all_stocks = query("SELECT stock_code FROM stocks WHERE stock_code NOT LIKE '688%%' AND stock_code NOT LIKE '300%%' AND stock_code NOT LIKE '830%%'")
    if not all_stocks:
        return []

    surge_records = detect_volume_surge(all_stocks, lookback_months, vol_min, vol_max)
    if not surge_records:
        return []

    if strategy_id == 'volume_surge_consecutive_king':
        results = detect_consecutive_kings(surge_records, shrink_days, min_gap, max_gap)
    else:
        results = detect_three_stage_kings(surge_records, shrink_days)

    if results:
        codes = [r['stock_code'] for r in results]
        placeholders = ','.join(['%s'] * len(codes))
        name_rows = query(f"SELECT stock_code, stock_name FROM stocks WHERE stock_code IN ({placeholders})", codes)
        name_map = {r['stock_code']: r['stock_name'] for r in name_rows}
        for r in results:
            r['stock_name'] = name_map.get(r['stock_code'], '')

        sector_sql = f"""
            SELECT ss.stock_code, s.sector_name, s.category
            FROM stock_sectors ss
            JOIN sectors s ON s.sector_code = ss.sector_code
            WHERE ss.stock_code IN ({placeholders})
              AND s.category IN ('industry', 'concept')
              AND s.level = 0
            ORDER BY ss.stock_code, s.category, s.sector_name
        """
        sector_rows = query(sector_sql, codes)
        sector_map = {}
        for sr in sector_rows:
            code = sr['stock_code']
            cat = sr['category']
            if code not in sector_map:
                sector_map[code] = {'industry': [], 'concept': []}
            sector_map[code][cat].append(sr['sector_name'])
        for r in results:
            info = sector_map.get(r['stock_code'], {'industry': [], 'concept': []})
            r['industry_sectors'] = ','.join(info['industry'][:3])
            r['concept_sectors'] = ','.join(info['concept'][:5])

    return results


def get_stock_volume_surge_detail(stock_code, lookback_months=6, vol_min=1.5, vol_max=4.0, shrink_days=3, min_gap=3, max_gap=10):
    stock_row = query("SELECT stock_code FROM stocks WHERE stock_code = %s", [stock_code])
    if not stock_row:
        return None

    surges = detect_volume_surge(stock_row, lookback_months, vol_min, vol_max)
    if not surges:
        return {'stock_code': stock_code, 'surges': [], 'three_stage_kings': [], 'consecutive_kings': [], 'all_king_surges': []}

    kings = detect_three_stage_kings(surges, shrink_days)
    consecutive = detect_consecutive_kings(surges, shrink_days, min_gap, max_gap)

    all_king_surges = []
    king_idx = 1
    for s in surges:
        if hasattr(s['trade_date'], 'strftime'):
            s_date = s['trade_date']
        else:
            from datetime import datetime
            s_date = datetime.strptime(str(s['trade_date'])[:10], '%Y-%m-%d')
        if check_king_surge(stock_code, s_date, shrink_days):
            date_str = s_date.strftime('%Y-%m-%d') if hasattr(s_date, 'strftime') else str(s_date)[:10]
            all_king_surges.append({
                'date': date_str,
                'close': float(s['close_price']),
                'ratio': float(s['vol_ratio']),
                'king_index': king_idx,
            })
            king_idx += 1

    for s in surges:
        if hasattr(s['trade_date'], 'strftime'):
            s['trade_date'] = s['trade_date'].strftime('%Y-%m-%d')
        else:
            s['trade_date'] = str(s['trade_date'])[:10]

    return {
        'stock_code': stock_code,
        'surges': surges,
        'three_stage_kings': kings,
        'consecutive_kings': consecutive,
        'all_king_surges': all_king_surges,
    }
